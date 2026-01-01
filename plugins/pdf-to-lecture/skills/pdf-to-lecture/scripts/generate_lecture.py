#!/usr/bin/env python3
"""
Lecture Generator - One command PDF to video lecture
Generates scripts using Claude Code CLI, then creates video with Indian TTS

OPTIMIZED VERSION: Eliminates sequential bottlenecks
- PDF text extraction: single pdfplumber pass
- PDF to images: single pdf2image pass
- Script generation: single Claude Code CLI call (all slides)
- Audio synthesis: parallel TTS using ThreadPool
- Video assembly: single ffmpeg concat command

NOTE: Uses Claude Code CLI (subscription-authenticated) instead of Anthropic API.
Requires 'claude' command to be available in PATH.

Usage:
    python generate_lecture.py --pdf slides.pdf --output lecture.mp4 --topic "Cell Biology"

Test with 3 slides:
    python generate_lecture.py --pdf slides.pdf --output test.mp4 --topic "Cell Biology" --max-slides 3
"""

import json
import os
import sys
import argparse
import tempfile
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Indian English voices
INDIAN_VOICES = {
    "male_a": "en-IN-Wavenet-B",
    "male_b": "en-IN-Wavenet-C",
    "female_a": "en-IN-Wavenet-A",
    "female_b": "en-IN-Wavenet-D",
    "male_standard": "en-IN-Standard-B",
    "female_standard": "en-IN-Standard-A"
}

# Default credentials path
DEFAULT_CREDS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "google_tts_credentials.json")

try:
    from google.cloud import texttospeech
except ImportError:
    texttospeech = None


def extract_text_from_pdf(pdf_path: str, max_pages: int = None) -> list:
    """Extract text from each page of PDF - single pass"""
    try:
        import pdfplumber
        texts = []
        with pdfplumber.open(pdf_path) as pdf:
            pages = pdf.pages[:max_pages] if max_pages else pdf.pages
            for page in pages:
                text = page.extract_text() or ""
                texts.append(text)
        return texts
    except ImportError:
        print("WARNING: pdfplumber not installed. Run: pip install pdfplumber")
        return None


def extract_slides_as_images(pdf_path: str, output_dir: str, max_slides: int = None) -> list:
    """Extract PDF pages as images - single pass"""
    try:
        from pdf2image import convert_from_path
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        if max_slides:
            images = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=max_slides)
        else:
            images = convert_from_path(pdf_path, dpi=150)

        paths = []
        for i, img in enumerate(images, 1):
            path = f"{output_dir}/slide_{i:03d}.png"
            img.save(path, "PNG")
            paths.append(path)
        return paths
    except ImportError:
        raise ImportError("pdf2image required. Run: pip install pdf2image")


def generate_scripts_with_claude(
    topic: str,
    num_slides: int,
    slide_texts: list = None,
    target_duration_per_slide: int = 60
) -> list:
    """Generate all lecture scripts using Claude Code CLI (subscription-authenticated)"""

    # Build context
    slide_context = ""
    if slide_texts:
        for i, text in enumerate(slide_texts, 1):
            if text.strip():
                slide_context += f"\n--- Slide {i} ---\n{text[:500]}\n"

    words_per_slide = 175  # Padded to ensure minimum 60 seconds of audio per slide

    prompt = f"""Generate lecture scripts for a {num_slides}-slide presentation on "{topic}".

CRITICAL REQUIREMENTS - FOLLOW EXACTLY:
- Write EXACTLY {num_slides} separate scripts, one for each slide
- Each script MUST be MINIMUM {words_per_slide} words. NOT LESS. Count your words.
- Target: {words_per_slide}-{words_per_slide + 30} words per script = {target_duration_per_slide} seconds of speech
- If a script is under {words_per_slide} words, YOU HAVE FAILED. Add more explanation, examples, context.
- Speak naturally as a professor would to students
- NO bullet points, NO timing markers, NO slide numbers
- Include transitions between slides
- Add context, examples, elaboration - professors don't just read slides, they TEACH

{f"SLIDE CONTENT FOR CONTEXT:{slide_context}" if slide_context else ""}

OUTPUT FORMAT:
Return ONLY a JSON array with exactly {num_slides} strings.
Example: ["Script for slide 1...", "Script for slide 2...", ...]
Do NOT include any markdown formatting, code blocks, or explanatory text - JUST the raw JSON array.
"""

    # Use Claude Code CLI instead of API
    # Increase timeout for large presentations (10 min for 50+ slides)
    timeout_seconds = max(300, num_slides * 12)  # ~12 sec per slide minimum
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text"],
        capture_output=True,
        text=True,
        timeout=timeout_seconds
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {result.stderr}")

    content = result.stdout.strip()

    # Clean markdown if present
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines)

    # Try to find JSON array in response
    if "[" in content:
        start = content.find("[")
        end = content.rfind("]") + 1
        content = content[start:end]

    scripts = json.loads(content)

    if len(scripts) != num_slides:
        raise ValueError(f"Generated {len(scripts)} scripts but need {num_slides}")

    return scripts


def synthesize_audio(text: str, output_path: str, voice: str = "en-IN-Wavenet-B", speaking_rate: float = 0.9):
    """Generate audio using Google Cloud TTS - single call"""
    if not texttospeech:
        raise ImportError("google-cloud-texttospeech required. Run: pip install google-cloud-texttospeech")

    client = texttospeech.TextToSpeechClient()

    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice_params = texttospeech.VoiceSelectionParams(
        language_code="en-IN",
        name=voice
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=speaking_rate
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice_params,
        audio_config=audio_config
    )

    with open(output_path, "wb") as f:
        f.write(response.audio_content)

    return output_path


def synthesize_all_audio_parallel(scripts: list, audio_dir: Path, voice_name: str, speaking_rate: float, max_workers: int = 5):
    """Synthesize all audio files in parallel using ThreadPool"""
    audio_paths = []

    def synthesize_slide(args):
        i, script = args
        audio_path = audio_dir / f"slide_{i:03d}.mp3"
        synthesize_audio(script, str(audio_path), voice_name, speaking_rate)
        return i, str(audio_path)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(synthesize_slide, (i, script)): i
                   for i, script in enumerate(scripts, 1)}

        results = {}
        for future in as_completed(futures):
            i, path = future.result()
            results[i] = path
            print(f"  Audio {i}/{len(scripts)} complete")

    # Return in order
    return [results[i] for i in range(1, len(scripts) + 1)]


def get_audio_duration(audio_path: str) -> float:
    """Get duration of audio file using ffprobe"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def create_video_config(slide_paths: list, audio_paths: list, config_path: str) -> dict:
    """Generate JSON config for video assembly"""
    config = {
        "slides": []
    }

    for slide_path, audio_path in zip(slide_paths, audio_paths):
        duration = get_audio_duration(audio_path)
        config["slides"].append({
            "image": slide_path,
            "audio": audio_path,
            "duration": duration
        })

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    return config


def assemble_video_from_config(config: dict, output_path: str, work_dir: Path):
    """Single ffmpeg call to create final video from config"""

    # Build ffmpeg filter complex for all slides
    inputs = []
    filter_parts = []
    concat_inputs = []

    for i, slide in enumerate(config["slides"]):
        # Add image and audio inputs
        inputs.extend(["-loop", "1", "-t", str(slide["duration"]), "-i", slide["image"]])
        inputs.extend(["-i", slide["audio"]])

        # Video stream: scale and format
        filter_parts.append(f"[{i*2}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]")
        concat_inputs.append(f"[v{i}][{i*2+1}:a]")

    # Concat all streams
    filter_complex = ";".join(filter_parts)
    filter_complex += f";{''.join(concat_inputs)}concat=n={len(config['slides'])}:v=1:a=1[outv][outa]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        output_path
    ]

    subprocess.run(cmd, check=True, capture_output=True)


def generate_lecture(
    pdf_path: str,
    output_path: str,
    topic: str = None,
    scripts: list = None,
    voice: str = "male_a",
    speaking_rate: float = 0.9,
    duration_per_slide: int = 60,
    max_slides: int = None,
    credentials_path: str = None
):
    """Generate complete lecture from PDF - optimized workflow"""

    # Set Google credentials if provided
    if credentials_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    elif os.path.exists(DEFAULT_CREDS_PATH):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = DEFAULT_CREDS_PATH

    work_dir = Path(tempfile.mkdtemp(prefix="lecture_"))

    try:
        # STEP 1 & 2: Extract text and images in sequence (both are single-pass)
        print("Step 1: Extracting text from PDF...")
        slide_texts = extract_text_from_pdf(pdf_path, max_slides)

        print("Step 2: Converting slides to images...")
        slides_dir = work_dir / "slides"
        slide_paths = extract_slides_as_images(pdf_path, str(slides_dir), max_slides)
        num_slides = len(slide_paths)
        print(f"  {num_slides} slides extracted")

        # STEP 3: Single Claude API call for all scripts
        if scripts is None:
            if not topic:
                raise ValueError("Either topic or scripts must be provided")

            print("Step 3: Generating all scripts with Claude (single API call)...")
            scripts = generate_scripts_with_claude(
                topic=topic,
                num_slides=num_slides,
                slide_texts=slide_texts,
                target_duration_per_slide=duration_per_slide
            )
            print(f"  {len(scripts)} scripts generated")

            # Save scripts for reference
            scripts_file = work_dir / "scripts.json"
            with open(scripts_file, "w") as f:
                json.dump(scripts, f, indent=2)

        # Limit scripts if max_slides specified
        if max_slides and len(scripts) > max_slides:
            scripts = scripts[:max_slides]

        # Get voice name
        voice_name = INDIAN_VOICES.get(voice, voice)

        # STEP 4: Parallel TTS for all audio
        print("Step 4: Synthesizing audio in parallel...")
        audio_dir = work_dir / "audio"
        audio_dir.mkdir()
        audio_paths = synthesize_all_audio_parallel(scripts, audio_dir, voice_name, speaking_rate)

        # STEP 5: Generate JSON config
        print("Step 5: Generating video assembly config...")
        config_path = work_dir / "video_config.json"
        config = create_video_config(slide_paths, audio_paths, str(config_path))

        # STEP 6: Single ffmpeg call to assemble video
        print("Step 6: Assembling final video (single ffmpeg call)...")
        assemble_video_from_config(config, output_path, work_dir)

        # Calculate stats
        total_duration = sum(slide["duration"] for slide in config["slides"])

        print("\n" + "="*50)
        print("LECTURE GENERATED SUCCESSFULLY!")
        print("="*50)
        print(f"Output: {output_path}")
        print(f"Slides: {num_slides}")
        print(f"Duration: {total_duration/60:.1f} minutes")

        return {"status": "success", "output_path": output_path}

    finally:
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="Generate video lecture from PDF slides",
        epilog="""
To set up Google Cloud TTS:
1. Create a service account at console.cloud.google.com
2. Enable Text-to-Speech API
3. Download JSON key
4. Either:
   - Save as data/google_tts_credentials.json
   - Or use --credentials flag
   - Or set GOOGLE_APPLICATION_CREDENTIALS env var
"""
    )
    parser.add_argument("--pdf", required=True, help="Path to PDF slides")
    parser.add_argument("--output", required=True, help="Output video path")
    parser.add_argument("--topic", help="Topic for script generation")
    parser.add_argument("--scripts", help="Path to existing scripts JSON")
    parser.add_argument("--voice", default="male_a", choices=list(INDIAN_VOICES.keys()))
    parser.add_argument("--rate", type=float, default=0.9, help="Speaking rate")
    parser.add_argument("--duration", type=int, default=60, help="Target seconds per slide")
    parser.add_argument("--max-slides", type=int, help="Limit to first N slides (for testing)")
    parser.add_argument("--credentials", help="Path to Google Cloud credentials JSON")

    args = parser.parse_args()

    if not args.topic and not args.scripts:
        parser.error("Either --topic or --scripts required")

    scripts = None
    if args.scripts:
        with open(args.scripts) as f:
            scripts = json.load(f)

    generate_lecture(
        pdf_path=args.pdf,
        output_path=args.output,
        topic=args.topic,
        scripts=scripts,
        voice=args.voice,
        speaking_rate=args.rate,
        duration_per_slide=args.duration,
        max_slides=args.max_slides,
        credentials_path=args.credentials
    )


if __name__ == "__main__":
    main()
