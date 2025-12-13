import os
from typing import List, Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel
import spacy
from spacytextblob.spacytextblob import SpacyTextBlob  # noqa: F401

from rustic_ai.core import Agent
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import ProcessContext
from rustic_ai.core.ui_protocol.types import TextFormat


class Publisher(BaseModel):
    name: Optional[str] = None
    site: Optional[str] = None


class ClaimReview(BaseModel):
    publisher: Publisher
    url: Optional[str] = None
    title: Optional[str] = None
    reviewDate: Optional[str] = None
    textualRating: Optional[str] = None
    languageCode: Optional[str] = None


class Claim(BaseModel):
    text: str
    claimant: Optional[str] = None
    claimDate: Optional[str] = None
    claimReview: List[ClaimReview] = []


class ClaimsResponse(BaseModel):
    claims: List[Claim]
    nextPageToken: Optional[str] = None


class FactCheckRespones(BaseModel):
    query: str
    claims: List[Claim]
    nextPageToken: Optional[str] = None


class FactCheckerAgent(Agent):
    def __init__(self):
        self._key = os.getenv("GOOGLE_CLOUD_API_KEY", None)
        if self._key:
            self.service = build("factchecktools", "v1alpha1", developerKey=self._key)
        else:
            self.service = build("factchecktools", "v1alpha1")

        self.nlp = spacy.load("en_core_web_sm")
        if "spacytextblob" not in self.nlp.pipe_names:
            self.nlp.add_pipe("spacytextblob", last=True)

    def _classify_textual_rating(self, text: str) -> str:
        if not text:
            return "Unknown"
        text = text.lower()

        # Terms that strongly indicate FALSE
        false_terms = [
            "false",
            "fake",
            "incorrect",
            "not true",
            "untrue",
            "debunked",
            "scam",
            "hoax",
            "baseless",
            "lie",
            "misleading",
            "exaggerated",
            "unsupported",
            "pants on fire",
            "pinocchio",
            "inaccurate",
            "wrong",
            "altered",
            "distorted",
            "rubbish",
            "nonsense",
            "bogus",
            "debunk",
        ]

        # Terms that indicate MIXED or UNCERTAIN but might contain "True" as substring
        unknown_terms = [
            "half true",
            "mixed",
            "unproven",
            "no evidence",
            "cherry picks",
        ]

        # Terms that indicate TRUE
        true_terms = [
            "true",
            "correct",
            "accurate",
            "fact",
            "real",
            "verified",
            "confirmed",
            "supported",
        ]

        # Check for False matches first
        for term in false_terms:
            if term in text:
                return "False"

        # Check for Unknown/Mixed matches
        for term in unknown_terms:
            if term in text:
                return "Unknown"

        # Check for True matches
        for term in true_terms:
            if term in text:
                return "True"

        # NLP Fallback
        if self.nlp:
            try:
                doc = self.nlp(text)
                polarity = doc._.blob.polarity
                # If polarity is strongly positive/negative, use it
                if polarity >= 0.1:
                    return "True"
                elif polarity <= -0.1:
                    return "False"
            except Exception as e:
                print(f"NLP error: {e}")

        return "Unknown"

    def calculate_verdict_and_supporting_urls(
        self, claims_response: ClaimsResponse, top_n: int = 3
    ) -> Tuple[str, List[str]]:
        """
        Analyzes textual ratings and:
        - Returns 'True', 'False', or 'Unknown' as final verdict.
        - Returns URLs of top n reviews supporting that verdict.
        """
        rated_reviews = []
        verdicts = []

        for claim in claims_response.claims:
            for review in claim.claimReview:
                if review.textualRating and review.url:
                    verdict = self._classify_textual_rating(review.textualRating.strip())
                    verdicts.append(verdict)
                    rated_reviews.append(
                        {
                            "url": review.url,
                            "verdict": verdict,
                            "textualRating": review.textualRating.strip(),
                        }
                    )

        if not rated_reviews:
            return "Unknown", []

        # Count True vs False.
        true_count = verdicts.count("True")
        false_count = verdicts.count("False")

        if false_count > true_count:
            final_verdict = "False"
        elif true_count > false_count:
            final_verdict = "True"
        else:
            final_verdict = "Unknown"

        # Filter reviews that match the final verdict
        if final_verdict != "Unknown":
            matching_reviews = [r for r in rated_reviews if r["verdict"] == final_verdict]
            top_urls = [r["url"] for r in matching_reviews[:top_n]]
        else:
            # If unknown, just return any URLs (preferring ones that had some rating if possible, but here all have ratings)
            top_urls = [r["url"] for r in rated_reviews[:top_n]]

        return final_verdict, top_urls

    def get_claims(self, query):
        try:
            response = self.service.claims().search(query=query, languageCode="en-US", alt="json").execute()
            if response:
                claims_response = ClaimsResponse.model_validate(response)
                return claims_response
        except HttpError as e:
            print("Error:", e.content)

    def render_verdict_markdown(self, query: str, verdict: str, urls: List[str]) -> str:
        """
        Renders a clean markdown string presenting the verdict and supporting links for the given query.
        """
        verdict_emoji = "✅" if verdict == "True" else "❌" if verdict == "False" else "⚠️"
        verdict_label = (
            "Likely TRUE" if verdict == "True" else "Likely FALSE" if verdict == "False" else "Not Determined"
        )

        md = f"🔍 **Query**: {query.strip()}<br>"
        md += f"**Verdict**: {verdict_emoji} {verdict_label}<br>"
        md += "**Based on analysis of expert reviews:**<br>"

        if urls:
            for url in set(urls):
                md += f"- {url}<br>"
        else:
            md += "\n No supporting sources available."

        return md

    @agent.processor(TextFormat)
    def process(self, ctx: ProcessContext[TextFormat]):
        query = ctx.payload.text

        claims_response = self.get_claims(query=query)
        if claims_response and claims_response.claims:
            final_verdict, urls = self.calculate_verdict_and_supporting_urls(claims_response=claims_response)
            response = self.render_verdict_markdown(query, final_verdict, urls)

            ctx.send(TextFormat(text=response))
            ctx.send(
                FactCheckRespones(
                    query=query, claims=claims_response.claims, nextPageToken=claims_response.nextPageToken
                )
            )
        else:
            ctx.send(TextFormat(text=f"🔍 No claims found for this claim: {query}<br>"))
