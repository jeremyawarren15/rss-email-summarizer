import os
import requests
from dotenv import load_dotenv
from typing import Dict
import logging

load_dotenv()

OLLAMA_API_URL = os.getenv('OLLAMA_API_URL')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3')
OLLAMA_TIMEOUT = int(os.getenv('OLLAMA_TIMEOUT', '60'))

# Parse whitelist and blacklist from env
EMAIL_WHITELIST = set(email.strip().lower() for email in os.getenv('EMAIL_WHITELIST', '').split(',') if email.strip())
EMAIL_BLACKLIST = set(email.strip().lower() for email in os.getenv('EMAIL_BLACKLIST', '').split(',') if email.strip())

def get_prompt_template():
    user_name = os.getenv('USER_NAME', 'the user')
    return (
        f"You are an email assistant for {user_name}. Analyze this email and determine if it's important.\n\n"
        f"IMPORTANT emails include:\n"
        f"- Personal messages from family, friends, colleagues, or acquaintances\n"
        f"- Social invitations, party planning, or event coordination\n"
        f"- Financial/banking communications\n"
        f"- Bills, invoices, or payment notifications\n"
        f"- Appointment confirmations or scheduling\n"
        f"- Work-related communications\n"
        f"- Legal or official documents\n"
        f"- Any message that requires a response or action from {user_name}\n\n"
        f"NOT IMPORTANT emails include:\n"
        f"- Marketing/promotional emails from businesses\n"
        f"- Newsletters or automated updates\n"
        f"- Spam or advertisements\n"
        f"- Generic notifications from services\n\n"
        f"If the email is from someone {user_name} knows personally (family, friends, colleagues), it is almost always IMPORTANT.\n\n"
        f"If the email is NOT IMPORTANT, respond with exactly: NOT IMPORTANT\n\n"
        f"If the email IS IMPORTANT, respond with a brief 1-2 sentence summary of what {user_name} needs to know or do. "
        f"Be direct and concise.\n\n"
        f"Email to analyze:\n"
        f"Subject: {{subject}}\n"
        f"From: {{from_addr}}\n"
        f"Date: {{date}}\n"
        f"Body: {{body}}\n"
    )

logger = logging.getLogger(__name__)

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
        response_text = data.get('response', '').strip()
        logger.info(f"LLM response:\n{response_text}")

        if response_text.upper().startswith('NOT IMPORTANT'):
            return {'is_important': False, 'summary': '', 'ai_summary': '', 'reason': None}

        # For important emails, the response is now clean summary text
        return {'is_important': True, 'summary': response_text, 'ai_summary': response_text, 'reason': None}
    except Exception as e:
        logger.error(f"Error from LLM: {e}")
        return {'is_important': False, 'summary': '', 'ai_summary': '', 'reason': f'Error: {e}'}