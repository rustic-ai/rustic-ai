import json
import logging
import os
from urllib.parse import urljoin

from rustic_ai.core.agents.utils.http_client import HttpClientMixin


class HuggingfaceInferenceMixin(HttpClientMixin):

    async def run_inference(
        self, model: str, prompt_payload: str, inference_endpoint: str = "https://api-inference.huggingface.co/models/"
    ):
        api_url = urljoin(inference_endpoint, model)

        headers = {}
        if not model or not isinstance(model, str):
            logging.info("model not provided")  # pragma: no cover
            return
        if not prompt_payload or not isinstance(prompt_payload, str):
            logging.info("prompt not provided")  # pragma: no cover
            return

        huggingface_api_key = os.getenv("HF_TOKEN", "")
        if huggingface_api_key:
            headers["Authorization"] = f"Bearer {huggingface_api_key}"

        try:
            response = await self.send_json(api_url, extra_headers=headers, json_data=prompt_payload)
            return response
        except Exception as e:
            logging.error(f"Error running inference: {e}")
            return None

    def generate_input_prompt(self, data: dict) -> str:
        return json.dumps({"inputs": data, "options": {"wait_for_model": True}})
