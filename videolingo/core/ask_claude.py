import json
import os
import time
from threading import Lock
from typing import Any, Callable, Dict, Optional

from anthropic import Anthropic
from requests.exceptions import RequestException
from videolingo.core.config_utils import load_key
from videolingo.core.api_utils import count_api_calls

LOG_FOLDER = "output/claude_log"
LOCK = Lock()


def save_log(model: str, prompt: str, response: Any, log_title: str = "default", message: Optional[str] = None) -> None:
    """Save the interaction log to a JSON file."""
    os.makedirs(LOG_FOLDER, exist_ok=True)
    log_data = {"model": model, "prompt": prompt, "response": response, "message": message}
    log_file = os.path.join(LOG_FOLDER, f"{log_title}.json")

    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            logs = json.load(f)
    else:
        logs = []
    logs.append(log_data)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=4)


def check_ask_claude_history(prompt: str, model: str, log_title: str) -> Any:
    """Check if the prompt has been asked before and return the cached response."""
    if not os.path.exists(LOG_FOLDER):
        return False
    file_path = os.path.join(LOG_FOLDER, f"{log_title}.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                if item["prompt"] == prompt:
                    return item["response"]
    return False


@count_api_calls
def ask_claude(
    prompt: str,
    response_json: bool = True,
    valid_def: Optional[Callable[[Dict], Dict]] = None,
    log_title: str = "default",
    system_prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 1.0,
) -> Any:
    """
    Send a request to Claude API and handle the response.

    Args:
        prompt: The user's input prompt
        response_json: Whether to expect and parse JSON response
        valid_def: Optional function to validate response format
        log_title: Title for logging the interaction
        system_prompt: Optional system prompt to set context
        max_tokens: Maximum tokens in the response
        temperature: Sampling temperature (0-2)

    Returns:
        Parsed JSON response or raw text response
    """
    # Load API configuration
    api_set = load_key("api")

    # Verify required configuration exists
    if not api_set.get("claude_key"):
        raise ValueError("⚠️ claude_key is missing in api configuration")
    if not api_set.get("claude_model"):
        raise ValueError("⚠️ claude_model is missing in api configuration")

    with LOCK:
        history_response = check_ask_claude_history(prompt, api_set["claude_model"], log_title)
        if history_response:
            return history_response

    # Configuration check already done above

    client = Anthropic(api_key=api_set["claude_key"])

    # Prepare the messages
    messages = [{"role": "user", "content": prompt}]

    # If JSON response is requested, add it to the system prompt
    final_system_prompt = system_prompt or ""
    if response_json:
        json_instruction = "Please provide your response in valid JSON format."
        final_system_prompt = f"{final_system_prompt}\n{json_instruction}" if final_system_prompt else json_instruction

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Prepare API call parameters
            api_params = {
                "model": api_set.get("claude_model", "claude-3-opus-20240229"),
                "messages": messages,
                "temperature": temperature,
            }

            # Add optional parameters only if they have valid values
            if final_system_prompt:
                api_params["system"] = final_system_prompt
            if isinstance(max_tokens, int) and max_tokens > 0:
                api_params["max_tokens"] = max_tokens

            response = client.messages.create(**api_params)

            response_content = response.content[0].text

            if response_json:
                try:
                    response_data = json.loads(response_content)

                    # Validate response if validation function provided
                    if valid_def:
                        valid_response = valid_def(response_data)
                        if valid_response["status"] != "success":
                            save_log(
                                api_set["claude_model"],
                                prompt,
                                response_data,
                                log_title="error",
                                message=valid_response["message"],
                            )
                            raise ValueError(f"❎ API response error: {valid_response['message']}")

                    break  # Successfully parsed JSON

                except json.JSONDecodeError as e:
                    print(f"❎ JSON parsing failed. Retrying: '''{response_content}'''")
                    save_log(
                        api_set["model"],
                        prompt,
                        response_content,
                        log_title="error",
                        message="JSON parsing failed.",
                    )
                    if attempt == max_retries - 1:
                        raise Exception(
                            f"JSON parsing still failed after {max_retries} attempts: {e}\n"
                            f"Please check your network connection or API key or `{LOG_FOLDER}/error.json` to debug."
                        )
            else:
                response_data = response_content
                break

        except Exception as e:
            if attempt < max_retries - 1:
                if isinstance(e, RequestException):
                    print(f"Request error: {e}. Retrying ({attempt + 1}/{max_retries})...")
                else:
                    print(f"Unexpected error occurred: {e}\nRetrying...")
                time.sleep(2)
            else:
                raise Exception(f"Still failed after {max_retries} attempts: {e}")

    with LOCK:
        if log_title != "None":
            save_log(api_set["model"], prompt, response_data, log_title=log_title)

    return response_data


if __name__ == "__main__":
    # Example usage
    response = ask_claude(
        "Return a simple JSON with status code 200.",
        response_json=True,
        log_title=None,
        system_prompt="You are a helpful assistant that provides JSON responses.",
        max_tokens=1000,  # Specify a valid integer
        temperature=1.0,
    )
    print(response)
