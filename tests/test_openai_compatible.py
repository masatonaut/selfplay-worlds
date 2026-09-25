"""OpenAICompatibleBackend against a fake server on localhost.

Checks the request we send and how the response is read, without any real
model or external network. Skipped unless the optional extra is installed:

    uv run --extra llm pytest tests/test_openai_compatible.py
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("openai")

from selfplay_worlds.inference import VLLMBackend  # noqa: E402

REPLY = {
    "id": "fake-1",
    "object": "chat.completion",
    "created": 0,
    "model": "fake-model",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"action": 1}'}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
}


@pytest.fixture
def fake_server():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append({"path": self.path, "body": json.loads(body)})
            payload = json.dumps(REPLY).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1", requests
    server.shutdown()


def test_request_and_response_round_trip(fake_server):
    base_url, requests = fake_server
    backend = VLLMBackend(model="fake-model", base_url=base_url)
    generation = backend.generate(messages=[{"role": "user", "content": "hi"}], max_tokens=20, temperature=0.0)
    assert generation.text == '{"action": 1}'
    assert generation.model == "fake-model"
    assert (generation.input_tokens, generation.output_tokens) == (12, 5)
    assert requests[0]["path"] == "/v1/chat/completions"
    assert requests[0]["body"]["model"] == "fake-model"
    assert requests[0]["body"]["max_tokens"] == 20
    assert requests[0]["body"]["messages"] == [{"role": "user", "content": "hi"}]
