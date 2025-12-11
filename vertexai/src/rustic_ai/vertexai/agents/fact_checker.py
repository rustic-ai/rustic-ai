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

    def calculate_verdict_and_supporting_urls(
        self, claims_response: ClaimsResponse, top_n: int = 3
    ) -> Tuple[str, List[str]]:
        """
        Analyzes sentiment of all textual ratings and:
        - Returns 'True' or 'False' as final verdict.
        - Returns URLs of top n reviews most strongly supporting that verdict.
        """
        rated_reviews = []

        for claim in claims_response.claims:
            for review in claim.claimReview:
                if review.textualRating and review.url:
                    doc = self.nlp(review.textualRating.strip())
                    polarity = doc._.blob.polarity
                    rated_reviews.append(
                        {"url": review.url, "polarity": polarity, "textualRating": review.textualRating.strip()}
                    )

        if not rated_reviews:
            return "Unknown", []

        # Calculate average polarity
        avg_polarity = sum(r["polarity"] for r in rated_reviews) / len(rated_reviews)
        verdict = "True" if avg_polarity >= 0 else "False"

        if verdict == "True":
            sorted_reviews = sorted(rated_reviews, key=lambda x: x["polarity"], reverse=True)
        else:
            sorted_reviews = sorted(rated_reviews, key=lambda x: x["polarity"])

        top_urls = [r["url"] for r in sorted_reviews[:top_n]]

        return verdict, top_urls

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
        else:
            ctx.send(TextFormat(text=f"🔍 No claims found for this claim: {query}<br>"))