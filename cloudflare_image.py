

import os
import base64
import requests
from dotenv import load_dotenv


# ============================================================
# LOAD .ENV
# ============================================================

load_dotenv()


# ============================================================
# CLOUDFLARE CREDENTIALS
# ============================================================

ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")


MODEL = "@cf/black-forest-labs/flux-1-schnell"


# ============================================================
# GENERATE IMAGE
# ============================================================

def generate_image(prompt, width=1024, height=1024):

    if not ACCOUNT_ID:
        raise RuntimeError(
            "CLOUDFLARE_ACCOUNT_ID is missing.\n\n"
            "Check your .env file."
        )

    if not API_TOKEN:
        raise RuntimeError(
            "CLOUDFLARE_API_TOKEN is missing.\n\n"
            "Check your .env file."
        )


    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{ACCOUNT_ID}/ai/run/{MODEL}"
    )


    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }


    payload = {
        "prompt": prompt,
        "steps": 4
    }


    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=180
        )

    except requests.RequestException as e:

        raise RuntimeError(
            f"Could not connect to Cloudflare:\n{e}"
        )


    # ========================================================
    # CHECK HTTP RESPONSE
    # ========================================================

    if response.status_code != 200:

        try:
            error_data = response.json()

        except Exception:
            error_data = response.text

        raise RuntimeError(
            f"Cloudflare HTTP {response.status_code}\n\n"
            f"{error_data}"
        )


    # ========================================================
    # PARSE RESPONSE
    # ========================================================

    try:

        data = response.json()

    except Exception:

        raise RuntimeError(
            "Cloudflare did not return JSON.\n\n"
            f"Response:\n{response.text[:1000]}"
        )


    # ========================================================
    # CHECK SUCCESS
    # ========================================================

    if not data.get("success"):

        raise RuntimeError(
            "Cloudflare returned an unsuccessful response:\n\n"
            + str(data)
        )


    result = data.get("result")


    if not result:

        raise RuntimeError(
            "Cloudflare response does not contain "
            "a result."
        )


    # ========================================================
    # GET BASE64 IMAGE
    # ========================================================

    image_base64 = result.get("image")


    if not image_base64:

        raise RuntimeError(
            "Cloudflare did not return an image."
        )


    # ========================================================
    # DECODE BASE64
    # ========================================================

    try:

        image_bytes = base64.b64decode(
            image_base64
        )

    except Exception as e:

        raise RuntimeError(
            f"Could not decode the generated image:\n{e}"
        )


    if not image_bytes:

        raise RuntimeError(
            "Cloudflare returned an empty image."
        )


    return image_bytes

