import os
import requests
from dotenv import load_dotenv
from typing import Dict
import logging
import re

load_dotenv()

OLLAMA_API_URL = os.getenv('OLLAMA_API_URL')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3')
OLLAMA_TIMEOUT = int(os.getenv('OLLAMA_TIMEOUT', '60'))
CLEAN_THINKING_CONTENT = os.getenv('CLEAN_THINKING_CONTENT', 'true').lower() == 'true'

# Parse whitelist and blacklist from env
EMAIL_WHITELIST = set(email.strip().lower() for email in os.getenv('EMAIL_WHITELIST', '').split(',') if email.strip())
EMAIL_BLACKLIST = set(email.strip().lower() for email in os.getenv('EMAIL_BLACKLIST', '').split(',') if email.strip())

def get_prompt_template():
    """
    Load the system prompt template from the markdown file and substitute the user name.
    """
    user_name = os.getenv('USER_NAME', 'the user')

    # Get the directory of this script to find the prompt file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_file_path = os.path.join(script_dir, 'system_prompt.md')

    try:
        with open(prompt_file_path, 'r', encoding='utf-8') as file:
            prompt_template = file.read()

        # Replace the user_name placeholder
        prompt_template = prompt_template.replace('{user_name}', user_name)

        return prompt_template
    except FileNotFoundError:
        logger.error(f"System prompt file not found at {prompt_file_path}")
        # Fallback to a basic prompt if the file is missing
        return f"You are an email assistant for {user_name}. Analyze this email and determine if it's important. Respond with 'NOT IMPORTANT' if not important, or provide a brief summary if important.\n\nEmail to analyze:\nSubject: {{subject}}\nFrom: {{from_addr}}\nDate: {{date}}\nBody: {{body}}"
    except Exception as e:
        logger.error(f"Error reading system prompt file: {e}")
        # Fallback to a basic prompt if there's an error
        return f"You are an email assistant for {user_name}. Analyze this email and determine if it's important. Respond with 'NOT IMPORTANT' if not important, or provide a brief summary if important.\n\nEmail to analyze:\nSubject: {{subject}}\nFrom: {{from_addr}}\nDate: {{date}}\nBody: {{body}}"

logger = logging.getLogger(__name__)

def clean_llm_response(response_text: str) -> str:
    """
    Clean LLM response by removing thinking/reasoning content from models like DeepSeek-R1.

    Args:
        response_text: Raw response from the LLM

    Returns:
        Cleaned response with thinking content removed
    """
    if not response_text:
        return response_text

    # Remove XML-style thinking tags (case-insensitive)
    thinking_patterns = [
        r'<thinking>.*?</thinking>',
        r'<think>.*?</think>',
        r'<reasoning>.*?</reasoning>',
        r'<thought>.*?</thought>',
        r'<analysis>.*?</analysis>',
        r'<考虑>.*?</考虑>',  # Chinese thinking tags
        r'<思考>.*?</思考>',  # Chinese thinking tags
    ]

    cleaned_text = response_text
    for pattern in thinking_patterns:
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.DOTALL | re.IGNORECASE)

    # Remove common thinking phrases at the start
    thinking_starts = [
        r'^Let me think about this.*?\n\n',
        r'^Let me analyze.*?\n\n',
        r'^I need to.*?\n\n',
        r'^First, let me.*?\n\n',
        r'^Looking at this.*?\n\n',
    ]

    for pattern in thinking_starts:
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.MULTILINE | re.IGNORECASE)

    # Clean up extra whitespace
    cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text)  # Multiple newlines
    cleaned_text = cleaned_text.strip()

    return cleaned_text

def summarize_email(subject: str, from_name: str, date: str, body: str) -> Dict:
    """
    Send the email to Ollama for importance filtering and summarization.
    Returns: {'is_important': bool, 'summary': str, 'ai_summary': str, 'reason': str or None}
    """
    from_name_lower = (from_name or '').lower()
    # Whitelist: always important
    if any(whitelisted in from_name_lower for whitelisted in EMAIL_WHITELIST):
        return {'is_important': True, 'summary': body[:500] + ('...' if len(body) > 500 else ''), 'ai_summary': body[:500] + ('...' if len(body) > 500 else ''), 'reason': 'Sender is whitelisted'}
    # Blacklist: always not important
    if any(blacklisted in from_name_lower for blacklisted in EMAIL_BLACKLIST):
        return {'is_important': False, 'summary': '', 'ai_summary': '', 'reason': 'Sender is blacklisted'}
    prompt_template = get_prompt_template()
    prompt = prompt_template.format(subject=subject, from_addr=from_name, date=date, body=body)
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }
    try:
        resp = requests.post(OLLAMA_API_URL, json=payload, timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        raw_response = data.get('response', '').strip()
        logger.info(f"Raw LLM response:\n{raw_response}")

        # Clean the response to remove thinking content (if enabled)
        if CLEAN_THINKING_CONTENT:
            response_text = clean_llm_response(raw_response)
            logger.info(f"Cleaned LLM response:\n{response_text}")
        else:
            response_text = raw_response
            logger.info("Thinking content cleaning is disabled")

        if response_text.upper().startswith('NOT IMPORTANT'):
            return {'is_important': False, 'summary': '', 'ai_summary': '', 'reason': None}

        # For important emails, the response is now clean summary text
        return {'is_important': True, 'summary': response_text, 'ai_summary': response_text, 'reason': None}
    except Exception as e:
        logger.error(f"Error from LLM: {e}")
        return {'is_important': False, 'summary': '', 'ai_summary': '', 'reason': f'Error: {e}'}