import os
from io import BytesIO

import cv2
import numpy as np

from PIL import Image, ImageFilter
from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# CLOUDFLARE CONFIGURATION
# ============================================================

ACCOUNT_ID = os.getenv(
    "CLOUDFLARE_ACCOUNT_ID"
)

API_TOKEN = os.getenv(
    "CLOUDFLARE_API_TOKEN"
)


INPAINT_MODEL = (
    "@cf/runwayml/stable-diffusion-v1-5-inpainting"
)


# ============================================================
# MODEL SETTINGS
# ============================================================

MIN_SIZE = 256
MAX_SIZE = 2048

NUM_STEPS = 20

GUIDANCE = 7.5

STRENGTH = 0.80


# ============================================================
# CREDENTIAL CHECK
# ============================================================

def _check_credentials():

    if not ACCOUNT_ID:

        raise RuntimeError(
            "CLOUDFLARE_ACCOUNT_ID is not configured."
        )

    if not API_TOKEN:

        raise RuntimeError(
            "CLOUDFLARE_API_TOKEN is not configured."
        )


# ============================================================
# OPEN IMAGE
# ============================================================

def _open_image(image_bytes):

    if not image_bytes:

        raise ValueError(
            "Image data is empty."
        )

    try:

        image = Image.open(
            BytesIO(image_bytes)
        ).convert("RGB")

        image.load()

        return image

    except Exception as e:

        raise ValueError(
            f"Could not open image: {e}"
        )


# ============================================================
# ROUND DIMENSION
# ============================================================

def _round_to_8(value):

    value = int(value)

    value = max(
        MIN_SIZE,
        min(
            value,
            MAX_SIZE
        )
    )

    value = (
        value // 8
    ) * 8

    return max(
        MIN_SIZE,
        value
    )


# ============================================================
# MODEL DIMENSIONS
# ============================================================

def _model_dimensions(
    width,
    height
):

    scale = min(
        1.0,
        1024 / max(
            width,
            height
        )
    )

    model_width = _round_to_8(
        width * scale
    )

    model_height = _round_to_8(
        height * scale
    )

    return (
        model_width,
        model_height
    )


# ============================================================
# PREPARE IMAGE
# ============================================================

def _prepare_image(
    image,
    width,
    height
):

    if not isinstance(
        image,
        Image.Image
    ):

        image = _open_image(
            image
        )

    image = image.convert(
        "RGB"
    )

    image = image.resize(
        (
            width,
            height
        ),
        Image.Resampling.LANCZOS
    )

    output = BytesIO()

    image.save(
        output,
        format="PNG"
    )

    return output.getvalue()


# ============================================================
# READ MASK
# ============================================================

def _read_mask(mask_bytes):

    if not mask_bytes:

        raise ValueError(
            "Mask data is empty."
        )

    try:

        mask = Image.open(
            BytesIO(mask_bytes)
        ).convert("L")

        mask.load()

        return mask

    except Exception as e:

        raise ValueError(
            f"Could not open mask: {e}"
        )


# ============================================================
# PREPARE MASK
# ============================================================

def _prepare_mask(
    mask_bytes,
    width,
    height
):

    mask = _read_mask(
        mask_bytes
    )

    mask = mask.resize(
        (
            width,
            height
        ),
        Image.Resampling.NEAREST
    )

    mask = np.array(
        mask,
        dtype=np.uint8
    )

    # Convert to binary mask
    mask = np.where(
        mask >= 128,
        255,
        0
    ).astype(
        np.uint8
    )

    # Slightly expand the selected area
    kernel = np.ones(
        (3, 3),
        np.uint8
    )

    mask = cv2.dilate(
        mask,
        kernel,
        iterations=1
    )

    if not np.any(
        mask > 0
    ):

        raise ValueError(
            "Mask is empty. "
            "Please select an area."
        )

    return mask


# ============================================================
# MASK TO API ARRAY
# ============================================================

def _mask_to_api_array(
    mask
):

    return mask.flatten().tolist()


# ============================================================
# CLOUDFLARE REQUEST
# ============================================================

def _run_cloudflare(
    payload
):

    _check_credentials()

    import requests

    url = (
        "https://api.cloudflare.com/client/v4/"
        f"accounts/{ACCOUNT_ID}/ai/run/"
        f"{INPAINT_MODEL}"
    )

    headers = {

        "Authorization":
            f"Bearer {API_TOKEN}",

        "Content-Type":
            "application/json"
    }

    try:

        response = requests.post(

            url,

            headers=headers,

            json=payload,

            timeout=180
        )

    except requests.Timeout:

        raise RuntimeError(
            "Cloudflare request timed out."
        )

    except requests.RequestException as e:

        raise RuntimeError(
            f"Cloudflare request failed: {e}"
        )


    # ========================================================
    # HTTP ERROR
    # ========================================================

    if response.status_code >= 400:

        try:

            error_data = (
                response.json()
            )

        except Exception:

            error_data = response.text

        raise RuntimeError(
            "Cloudflare rejected the request. "
            f"HTTP {response.status_code} "
            f"{error_data}"
        )


    # ========================================================
    # RESPONSE
    # ========================================================

    content_type = (
        response.headers
        .get(
            "content-type",
            ""
        )
        .lower()
    )


    # --------------------------------------------------------
    # Direct image response
    # --------------------------------------------------------

    if (
        "image" in content_type
        or
        "octet-stream" in content_type
    ):

        if not response.content:

            raise RuntimeError(
                "Cloudflare returned an empty image."
            )

        return response.content


    # --------------------------------------------------------
    # JSON response
    # --------------------------------------------------------

    try:

        data = response.json()

    except Exception as e:

        raise RuntimeError(
            "Cloudflare returned an invalid response: "
            f"{e}"
        )


    if not data.get(
        "success",
        False
    ):

        raise RuntimeError(
            f"Cloudflare AI request failed: {data}"
        )


    result = data.get(
        "result"
    )


    if not result:

        raise RuntimeError(
            "Cloudflare returned no result."
        )


    # ========================================================
    # BASE64 IMAGE
    # ========================================================

    if isinstance(
        result,
        dict
    ):

        image_data = result.get(
            "image"
        )

        if image_data:

            import base64

            try:

                return base64.b64decode(
                    image_data
                )

            except Exception as e:

                raise RuntimeError(
                    "Could not decode Cloudflare "
                    f"image: {e}"
                )


    raise RuntimeError(
        "Cloudflare response did not contain "
        "valid image data."
    )


# ============================================================
# COMPOSITE RESULT
# ============================================================

def _composite_result(
    original_image,
    generated_image,
    mask
):

    generated_image = (
        generated_image
        .resize(
            original_image.size,
            Image.Resampling.LANCZOS
        )
        .convert("RGB")
    )


    # Convert mask to PIL
    mask_image = Image.fromarray(
        mask,
        mode="L"
    )


    # Resize mask to original size
    mask_image = mask_image.resize(
        original_image.size,
        Image.Resampling.NEAREST
    )


    # Slight feathering
    mask_image = mask_image.filter(
        ImageFilter.GaussianBlur(
            radius=1.5
        )
    )


    return Image.composite(
        generated_image,
        original_image,
        mask_image
    )


# ============================================================
# LOCAL REMOVE OBJECT
# ============================================================

def _remove_object_local(
    image_bytes,
    mask_bytes
):

    # --------------------------------------------------------
    # Open original image
    # --------------------------------------------------------

    image = _open_image(
        image_bytes
    )


    # --------------------------------------------------------
    # Read mask
    # --------------------------------------------------------

    mask = _read_mask(
        mask_bytes
    )


    # --------------------------------------------------------
    # Resize mask
    # --------------------------------------------------------

    mask = mask.resize(
        image.size,
        Image.Resampling.NEAREST
    )


    mask_array = np.array(
        mask,
        dtype=np.uint8
    )


    # --------------------------------------------------------
    # Binary mask
    # --------------------------------------------------------

    mask_array = np.where(
        mask_array >= 128,
        255,
        0
    ).astype(
        np.uint8
    )


    # --------------------------------------------------------
    # Slightly expand mask
    # --------------------------------------------------------

    kernel = np.ones(
        (3, 3),
        np.uint8
    )

    mask_array = cv2.dilate(
        mask_array,
        kernel,
        iterations=1
    )


    if not np.any(
        mask_array > 0
    ):

        raise ValueError(
            "Selected mask is empty."
        )


    # --------------------------------------------------------
    # Convert image to OpenCV
    # --------------------------------------------------------

    image_array = np.array(
        image
    )


    # --------------------------------------------------------
    # OpenCV INPAINT
    # --------------------------------------------------------

    result = cv2.inpaint(

        image_array,

        mask_array,

        3,

        cv2.INPAINT_TELEA
    )


    # --------------------------------------------------------
    # Convert back to PIL
    # --------------------------------------------------------

    result_image = Image.fromarray(
        result
    ).convert("RGB")


    # --------------------------------------------------------
    # Output PNG
    # --------------------------------------------------------

    output = BytesIO()

    result_image.save(
        output,
        format="PNG"
    )

    return output.getvalue()


# ============================================================
# MAIN EDIT FUNCTION
# ============================================================

def edit_image(
    image_bytes,
    prompt,
    width=1024,
    height=1024,
    operation="Remove",
    mask_bytes=None
):

    # ========================================================
    # VALIDATION
    # ========================================================

    if not image_bytes:

        raise ValueError(
            "Input image is empty."
        )


    if not prompt or not prompt.strip():

        raise ValueError(
            "Editing prompt cannot be empty."
        )


    if not mask_bytes:

        raise ValueError(
            "Please select an area on the image."
        )


    operation = (
        operation
        .strip()
        .lower()
    )


    # ========================================================
    # REMOVE OBJECT
    # ========================================================

    if operation == "remove":

        return _remove_object_local(

            image_bytes,

            mask_bytes
        )


    # ========================================================
    # OTHER OPERATIONS
    # ========================================================

    raise ValueError(
        "Only Remove operation is supported "
        "in this version."
    )


# ============================================================
# REMOVE OBJECT WRAPPER
# ============================================================

def remove_object(
    image_bytes,
    prompt,
    width=1024,
    height=1024,
    mask_bytes=None
):

    return edit_image(

        image_bytes=image_bytes,

        prompt=prompt,

        width=width,

        height=height,

        operation="Remove",

        mask_bytes=mask_bytes
    )