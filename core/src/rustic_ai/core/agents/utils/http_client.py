import aiohttp


class HttpClientMixin:
    json_headers = {"Content-Type": "application/json", "Accept": "application/json"}

    async def send_json(self, url, json_data, extra_headers=None):
        if extra_headers:
            headers = {**self.json_headers, **extra_headers}
        else:
            headers = self.json_headers
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=json_data) as response:
                response.raise_for_status()
                r = await response.json()
                return r
