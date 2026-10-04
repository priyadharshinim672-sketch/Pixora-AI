
import hashlib
import time
from io import BytesIO
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace

import streamlit as st
from PIL import Image, ImageFilter
import numpy as np

from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Pixora AI",
    page_icon="✨",
    layout="wide"
)


# ============================================================
# STREAMLIT DRAWABLE CANVAS COMPATIBILITY
# ============================================================

try:

    import streamlit.elements.image as st_image
    from streamlit.elements.lib import image_utils

    _original_image_to_url = image_utils.image_to_url

    def _pixora_image_to_url(
        image,
        width=None,
        clamp=False,
        channels="RGB",
        output_format="PNG",
        image_id=None
    ):

        if isinstance(width, int):

            layout_config = SimpleNamespace(
                width=width
            )

        elif width is None:

            layout_config = SimpleNamespace(
                width=None
            )

        else:

            layout_config = width

        try:

            return _original_image_to_url(
                image,
                layout_config,
                clamp,
                channels,
                output_format,
                image_id
            )

        except TypeError:

            return _original_image_to_url(
                image=image,
                layout_config=layout_config,
                clamp=clamp,
                channels=channels,
                output_format=output_format,
                image_id=image_id
            )

    st_image.image_to_url = _pixora_image_to_url

except Exception:
    pass


# ============================================================
# DRAWABLE CANVAS
# ============================================================

try:

    from streamlit_drawable_canvas import st_canvas

    CANVAS_AVAILABLE = True

except Exception:

    CANVAS_AVAILABLE = False


# ============================================================
# IMAGE GENERATION
# ============================================================

try:

    from cloudflare_image import generate_image

except Exception:

    generate_image = None


# ============================================================
# IMAGE EDITING
# ============================================================

try:

    from cloudflare_edit import edit_image

except Exception:

    edit_image = None


# ============================================================
# VOICE RECOGNITION
# ============================================================

try:

    import speech_recognition as sr

    SPEECH_AVAILABLE = True

except Exception:

    sr = None
    SPEECH_AVAILABLE = False


# ============================================================
# SESSION STATE
# ============================================================

DEFAULTS = {

    # --------------------------------------------------------
    # CREATE
    # --------------------------------------------------------

    "prompt": "",

    "generated_image": None,

    "generated_bytes": None,

    "generated_path": None,


    # --------------------------------------------------------
    # EDIT - REMOVE ONLY
    # --------------------------------------------------------

    "original_image": None,

    "original_bytes": None,

    "edited_image": None,

    "edited_bytes": None,

    "edited_path": None,

    "uploaded_hash": None,

    "canvas_key": 0,

    "last_mask": None,

    "remove_description": "",


    # --------------------------------------------------------
    # VOICE
    # --------------------------------------------------------

    "last_create_audio_hash": None,

    "last_remove_audio_hash": None,
}


for key, value in DEFAULTS.items():

    if key not in st.session_state:

        st.session_state[key] = value


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

    .stApp {

        background:
            radial-gradient(
                circle at 10% 10%,
                rgba(255,190,235,0.20),
                transparent 25%
            ),
            radial-gradient(
                circle at 90% 10%,
                rgba(190,190,255,0.20),
                transparent 25%
            ),
            #faf9ff;
    }

    .main-title {

        text-align: center;

        font-size: 52px;

        font-weight: 800;

        margin-top: 20px;

        margin-bottom: 5px;
    }

    .subtitle {

        text-align: center;

        color: #77738b;

        font-size: 16px;

        margin-bottom: 30px;
    }

    .section-title {

        font-size: 28px;

        font-weight: 700;

        margin-top: 20px;
    }

    .canvas-help {

        padding: 14px 18px;

        border-radius: 12px;

        background: #f0edff;

        margin-bottom: 15px;

        border: 1px solid #ded8ff;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="main-title">✨ Pixora AI</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">'
    'Creative AI Studio • Imagine. Create. Transform.'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# MODE
# ============================================================

mode = st.radio(
    "Choose a mode",
    [
        "Create",
        "Edit"
    ],
    horizontal=True
)

st.divider()


# ============================================================
# VOICE → TEXT FUNCTION
# ============================================================

def convert_audio_to_text(audio_file):

    if not SPEECH_AVAILABLE:

        raise RuntimeError(
            "SpeechRecognition is not installed."
        )

    if audio_file is None:

        raise RuntimeError(
            "No audio was recorded."
        )

    try:

        audio_bytes = audio_file.getvalue()

        if not audio_bytes:

            raise RuntimeError(
                "Recorded audio is empty."
            )

        audio_source = sr.AudioFile(
            BytesIO(audio_bytes)
        )

        recognizer = sr.Recognizer()

        with audio_source as source:

            audio_data = recognizer.record(
                source
            )

        text = recognizer.recognize_google(
            audio_data,
            language="en-IN"
        )

        return text.strip()

    except sr.UnknownValueError:

        raise RuntimeError(
            "Sorry, I could not understand your voice."
        )

    except sr.RequestError as e:

        raise RuntimeError(
            f"Speech recognition service error: {e}"
        )

    except Exception as e:

        raise RuntimeError(
            f"Voice-to-text failed: {e}"
        )


# ============================================================
# CREATE MODE
# ============================================================

if mode == "Create":

    st.markdown(
        '<div class="section-title">'
        'Create an image'
        '</div>',
        unsafe_allow_html=True
    )


    # ========================================================
    # VOICE INPUT
    # ========================================================

    st.subheader("🎤 Voice to Text")

    if not SPEECH_AVAILABLE:

        st.error(
            "SpeechRecognition is not installed."
        )

        st.code(
            "python -m pip install SpeechRecognition"
        )

    else:

        st.caption(
            "Click the microphone, speak your image prompt, "
            "and the text will automatically appear below."
        )

        audio_prompt = st.audio_input(
            "🎙️ Record your image prompt",
            key="create_voice_input"
        )

        if audio_prompt is not None:

            try:

                audio_bytes = audio_prompt.getvalue()

                audio_hash = hashlib.sha256(
                    audio_bytes
                ).hexdigest()

                if (
                    audio_hash
                    != st.session_state.last_create_audio_hash
                ):

                    with st.spinner(
                        "Converting voice to text..."
                    ):

                        spoken_text = convert_audio_to_text(
                            audio_prompt
                        )

                    if spoken_text:

                        st.session_state.prompt = (
                            spoken_text
                        )

                        st.session_state.last_create_audio_hash = (
                            audio_hash
                        )

                        st.success(
                            f"Voice converted to text: "
                            f"{spoken_text}"
                        )

                        st.rerun()

            except Exception as e:

                st.error(
                    str(e)
                )


    # ========================================================
    # IMAGE PROMPT
    # ========================================================

    prompt = st.text_area(
        "Image prompt",
        value=st.session_state.prompt,
        placeholder=(
            "Example: A futuristic city at sunset "
            "with glowing buildings and flying cars"
        ),
        height=130
    )

    st.session_state.prompt = prompt


    # ========================================================
    # IMAGE SETTINGS
    # ========================================================

    st.subheader("Image Settings")

    c1, c2 = st.columns(2)

    with c1:

        width = st.selectbox(
            "Width",
            [
                512,
                768,
                1024
            ],
            index=2
        )

    with c2:

        height = st.selectbox(
            "Height",
            [
                512,
                768,
                1024
            ],
            index=2
        )


    # ========================================================
    # GENERATE
    # ========================================================

    if st.button(
        "✨ Generate Image",
        type="primary",
        use_container_width=True
    ):

        current_prompt = (
            st.session_state.prompt.strip()
        )

        if not current_prompt:

            st.warning(
                "Please enter an image prompt "
                "or use Voice to Text."
            )

        elif generate_image is None:

            st.error(
                "cloudflare_image.py could not be imported."
            )

        else:

            progress = st.progress(0)

            status = st.empty()

            try:

                status.info(
                    "Pixora is creating your image..."
                )

                for value in range(
                    0,
                    70,
                    5
                ):

                    progress.progress(value)

                    time.sleep(0.04)


                image_bytes = generate_image(
                    prompt=current_prompt,
                    width=width,
                    height=height
                )


                image = Image.open(
                    BytesIO(image_bytes)
                ).convert("RGB")

                image.load()


                progress.progress(100)

                status.success(
                    "Your image is ready!"
                )


                # =================================================
                # SAVE
                # =================================================

                folder = Path(
                    "generated_images"
                )

                folder.mkdir(
                    exist_ok=True
                )


                timestamp = datetime.now().strftime(
                    "%Y%m%d_%H%M%S"
                )


                save_path = (
                    folder
                    /
                    f"pixora_{timestamp}.png"
                )


                image.save(
                    save_path,
                    "PNG"
                )


                # =================================================
                # SESSION
                # =================================================

                st.session_state.generated_image = (
                    image
                )

                st.session_state.generated_bytes = (
                    image_bytes
                )

                st.session_state.generated_path = (
                    str(save_path)
                )


                time.sleep(0.2)

                progress.empty()


            except Exception as e:

                progress.empty()

                status.empty()

                st.error(
                    "Image generation failed."
                )

                st.exception(e)


    # ========================================================
    # RESULT
    # ========================================================

    if (
        st.session_state.generated_image
        is not None
    ):

        st.divider()

        st.subheader(
            "Your Creation"
        )


        st.image(
            st.session_state.generated_image,
            use_container_width=True
        )


        d1, d2 = st.columns(2)


        with d1:

            st.download_button(
                "Download PNG",

                data=(
                    st.session_state.generated_bytes
                ),

                file_name="pixora_creation.png",

                mime="image/png",

                use_container_width=True
            )


        with d2:

            jpeg_buffer = BytesIO()

            st.session_state.generated_image.save(
                jpeg_buffer,
                format="JPEG",
                quality=95
            )

            jpeg_buffer.seek(0)


            st.download_button(
                "Download JPEG",

                data=jpeg_buffer,

                file_name="pixora_creation.jpg",

                mime="image/jpeg",

                use_container_width=True
            )


# ============================================================
# EDIT MODE - REMOVE OBJECT ONLY
# ============================================================

else:

    st.markdown(
        '<div class="section-title">'
        'Remove an object'
        '</div>',
        unsafe_allow_html=True
    )

    st.caption(
        "Upload an image, describe the object you want "
        "to remove, and draw over it."
    )


    # ========================================================
    # CANVAS CHECK
    # ========================================================

    if not CANVAS_AVAILABLE:

        st.error(
            "streamlit-drawable-canvas is not installed."
        )

        st.code(
            "python -m pip install streamlit-drawable-canvas"
        )

        st.stop()


    # ========================================================
    # UPLOAD IMAGE
    # ========================================================

    uploaded_file = st.file_uploader(
        "Upload an image",
        type=[
            "png",
            "jpg",
            "jpeg",
            "webp"
        ],
        key="remove_image_uploader"
    )


    if uploaded_file is None:

        st.info(
            "Upload an image to start editing."
        )

        st.stop()


    original_bytes = (
        uploaded_file.getvalue()
    )


    current_hash = hashlib.sha256(
        original_bytes
    ).hexdigest()


    # ========================================================
    # NEW IMAGE
    # ========================================================

    if (
        current_hash
        != st.session_state.uploaded_hash
    ):

        try:

            image = Image.open(
                BytesIO(original_bytes)
            ).convert("RGB")

            image.load()

        except Exception as e:

            st.error(
                f"Could not open image: {e}"
            )

            st.stop()


        st.session_state.uploaded_hash = (
            current_hash
        )

        st.session_state.original_bytes = (
            original_bytes
        )

        st.session_state.original_image = (
            image
        )

        st.session_state.edited_image = None

        st.session_state.edited_bytes = None

        st.session_state.edited_path = None

        st.session_state.last_mask = None

        st.session_state.canvas_key += 1

        st.session_state.last_remove_audio_hash = (
            None
        )

        st.session_state.remove_description = (
            ""
        )


    original_image = (
        st.session_state.original_image
    )


    # ========================================================
    # ORIGINAL IMAGE
    # ========================================================

    st.subheader(
        "Original Image"
    )

    st.image(
        original_image,
        use_container_width=True
    )


    # ========================================================
    # OBJECT DESCRIPTION
    # ========================================================

    st.subheader(
        "What do you want to remove?"
    )


    # ========================================================
    # VOICE INPUT
    # ========================================================

    st.subheader(
        "🎤 Voice to Text"
    )


    if SPEECH_AVAILABLE:

        st.caption(
            "Speak the object you want to remove."
        )


        audio_remove = st.audio_input(
            "🎙️ Record object description",
            key="remove_voice_input"
        )


        if audio_remove is not None:

            try:

                audio_bytes = (
                    audio_remove.getvalue()
                )

                audio_hash = hashlib.sha256(
                    audio_bytes
                ).hexdigest()


                if (
                    audio_hash
                    != st.session_state.last_remove_audio_hash
                ):

                    with st.spinner(
                        "Converting voice to text..."
                    ):

                        spoken_text = (
                            convert_audio_to_text(
                                audio_remove
                            )
                        )


                    if spoken_text:

                        st.session_state.remove_description = (
                            spoken_text
                        )

                        st.session_state.last_remove_audio_hash = (
                            audio_hash
                        )


                        st.success(
                            f"Voice converted to text: "
                            f"{spoken_text}"
                        )


                        st.rerun()


            except Exception as e:

                st.error(
                    str(e)
                )


    else:

        st.warning(
            "SpeechRecognition is not installed."
        )


    # ========================================================
    # OBJECT DESCRIPTION INPUT
    # ========================================================

    object_description = st.text_input(
        "Object to remove",
        value=st.session_state.remove_description,
        placeholder="Example: the person"
    )


    st.session_state.remove_description = (
        object_description
    )


    # ========================================================
    # CANVAS INSTRUCTION
    # ========================================================

    st.caption(
        "Draw over the entire object you want "
        "Pixora to remove."
    )


    st.subheader(
        "Select the Area"
    )


    st.markdown(
        """
        <div class="canvas-help">
        Draw over the object you want Pixora to remove.
        </div>
        """,
        unsafe_allow_html=True
    )


    # ========================================================
    # CANVAS SIZE
    # ========================================================

    original_width, original_height = (
        original_image.size
    )


    MAX_CANVAS_WIDTH = 750


    scale = min(
        1.0,
        MAX_CANVAS_WIDTH / original_width
    )


    canvas_width = max(
        300,
        int(original_width * scale)
    )


    canvas_height = max(
        200,
        int(original_height * scale)
    )


    canvas_image = original_image.resize(
        (
            canvas_width,
            canvas_height
        ),
        Image.Resampling.LANCZOS
    )


    # ========================================================
    # BRUSH
    # ========================================================

    stroke_width = st.slider(
        "Brush size",
        min_value=5,
        max_value=100,
        value=35,
        step=5,
        key="remove_brush_size"
    )


    # ========================================================
    # DRAWABLE CANVAS
    # ========================================================

    try:

        canvas_result = st_canvas(

            fill_color=(
                "rgba(255, 0, 0, 0.45)"
            ),

            stroke_width=stroke_width,

            stroke_color="#ff0000",

            background_image=canvas_image,

            update_streamlit=True,

            height=canvas_height,

            width=canvas_width,

            drawing_mode="freedraw",

            display_toolbar=True,

            key=(
                f"pixora_remove_canvas_"
                f"{st.session_state.canvas_key}"
            )
        )


    except Exception as e:

        st.error(
            "The drawing canvas could not be created."
        )

        st.exception(e)

        st.stop()


    # ========================================================
    # CREATE MASK
    # ========================================================

    mask_bytes = None


    if (
        canvas_result is not None
        and canvas_result.image_data is not None
    ):

        try:

            canvas_data = (
                canvas_result.image_data
            )


            rgb = canvas_data[:, :, :3]


            red = rgb[:, :, 0].astype(
                np.int16
            )

            green = rgb[:, :, 1].astype(
                np.int16
            )

            blue = rgb[:, :, 2].astype(
                np.int16
            )


            # ------------------------------------------------
            # Detect red drawing
            # ------------------------------------------------

            selected = (
                (red > green + 25)
                &
                (red > blue + 25)
                &
                (red > 100)
            )


            mask_array = np.where(
                selected,
                255,
                0
            ).astype(
                np.uint8
            )


            if np.any(
                mask_array > 0
            ):

                mask_image = Image.fromarray(
                    mask_array,
                    mode="L"
                )


                # ------------------------------------------------
                # Convert canvas coordinates to original image
                # ------------------------------------------------

                mask_image = mask_image.resize(
                    original_image.size,
                    Image.Resampling.NEAREST
                )


                # ------------------------------------------------
                # Slightly expand selected region
                # ------------------------------------------------

                mask_image = mask_image.filter(
                    ImageFilter.MaxFilter(5)
                )


                mask_buffer = BytesIO()


                mask_image.save(
                    mask_buffer,
                    format="PNG"
                )


                mask_bytes = (
                    mask_buffer.getvalue()
                )


                st.session_state.last_mask = (
                    mask_bytes
                )


            else:

                mask_bytes = None


        except Exception as e:

            st.warning(
                f"Could not create mask: {e}"
            )


    # ========================================================
    # MASK PREVIEW
    # ========================================================

    if mask_bytes is not None:

        st.subheader(
            "Selected Area"
        )


        mask_preview = Image.open(
            BytesIO(mask_bytes)
        ).convert("L")


        st.image(
            mask_preview,
            caption="White area = selected object",
            use_container_width=True
        )


        st.success(
            "Selection detected."
        )


    else:

        st.info(
            "Draw over the object you want to remove."
        )


    # ========================================================
    # REMOVE BUTTON
    # ========================================================

    if st.button(
        "🗑️ Remove Object",
        type="primary",
        use_container_width=True
    ):


        # ----------------------------------------------------
        # DESCRIPTION VALIDATION
        # ----------------------------------------------------

        if not object_description.strip():

            st.warning(
                "Please describe the object you want "
                "to remove."
            )

            st.stop()


        # ----------------------------------------------------
        # MASK VALIDATION
        # ----------------------------------------------------

        if mask_bytes is None:

            st.warning(
                "Please draw over the object first."
            )

            st.stop()


        # ----------------------------------------------------
        # EDITOR VALIDATION
        # ----------------------------------------------------

        if edit_image is None:

            st.error(
                "cloudflare_edit.py could not be imported."
            )

            st.stop()


        progress = st.progress(0)

        status = st.empty()


        try:

            # =================================================
            # PREPARING
            # =================================================

            status.info(
                "Preparing the selected area..."
            )

            progress.progress(25)


            # =================================================
            # INSTRUCTION
            # =================================================

            instruction = (
                f"Remove "
                f"{object_description.strip()}."
            )


            # =================================================
            # PROCESS
            # =================================================

            status.info(
                "Pixora is removing the object..."
            )

            progress.progress(50)


            edited_bytes = edit_image(

                image_bytes=original_bytes,

                prompt=instruction,

                width=original_width,

                height=original_height,

                operation="Remove",

                mask_bytes=mask_bytes
            )


            progress.progress(80)


            # =================================================
            # OPEN RESULT
            # =================================================

            edited_image = Image.open(
                BytesIO(edited_bytes)
            ).convert("RGB")

            edited_image.load()


            progress.progress(100)


            status.success(
                "Object removed successfully!"
            )


            # =================================================
            # SAVE RESULT
            # =================================================

            folder = Path(
                "edited_images"
            )

            folder.mkdir(
                exist_ok=True
            )


            timestamp = datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )


            filename = (
                f"pixora_remove_{timestamp}.png"
            )


            save_path = (
                folder
                /
                filename
            )


            edited_image.save(
                save_path,
                "PNG"
            )


            # =================================================
            # SESSION STATE
            # =================================================

            st.session_state.edited_image = (
                edited_image
            )

            st.session_state.edited_bytes = (
                edited_bytes
            )

            st.session_state.edited_path = (
                str(save_path)
            )


            time.sleep(0.2)

            progress.empty()


        except Exception as e:

            progress.empty()

            status.empty()

            st.error(
                "Image removal failed."
            )

            st.exception(e)


    # ========================================================
    # RESULT
    # ========================================================

    if (
        st.session_state.edited_image
        is not None
    ):

        st.divider()


        st.subheader(
            "Before and After"
        )


        before, after = st.columns(2)


        # ====================================================
        # ORIGINAL
        # ====================================================

        with before:

            st.markdown(
                "**Original**"
            )


            st.image(
                st.session_state.original_image,
                use_container_width=True
            )


        # ====================================================
        # EDITED
        # ====================================================

        with after:

            st.markdown(
                "**After Removing Object**"
            )


            st.image(
                st.session_state.edited_image,
                use_container_width=True
            )


        # ====================================================
        # DOWNLOAD
        # ====================================================

        d1, d2 = st.columns(2)


        # ====================================================
        # PNG
        # ====================================================

        with d1:

            st.download_button(

                "Download PNG",

                data=(
                    st.session_state.edited_bytes
                ),

                file_name="pixora_removed.png",

                mime="image/png",

                use_container_width=True
            )


        # ====================================================
        # JPEG
        # ====================================================

        with d2:

            jpeg_buffer = BytesIO()


            st.session_state.edited_image.save(

                jpeg_buffer,

                format="JPEG",

                quality=95
            )


            jpeg_buffer.seek(0)


            st.download_button(

                "Download JPEG",

                data=jpeg_buffer,

                file_name="pixora_removed.jpg",

                mime="image/jpeg",

                use_container_width=True
            )


        # ====================================================
        # SAVE LOCATION
        # ====================================================

        st.success(
            "Saved to: "
            +
            st.session_state.edited_path
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Pixora AI • Imagine. Create. Transform."
)

