# TimeoutExpired error will get return if the timeout exceeded.
# env variables are passed as mapping with str:str. These are used instead of default process envrionment they said. Although I want to use default environment.
# If check is true, and the process exits with a non-zero exit code, a CalledProcessError exception will be raised. Attributes of that exception hold the arguments, the exit code, and stdout and stderr if they were captured.
"""
Takes model's generated markdown response and converts into pdf. Saves the pdf in the same directory as markdown.
"""

import subprocess
from pathlib import Path
import shutil
import logging
import sys

logger = logging.getLogger("make_sense.pandoc")


# def _prepend_to_file(model_response_filepath: Path, style_path: Path) -> None:
#     """
#     Creates a temp file, write style_path on top, write data inside model_reponse_filepath on bottom, changes temp file to model_response_filepath.
#     Args:
#         model_response_filepath (Path): Path to the _model_response.md
#         style_path (Path): Path to the pdf_style.md
#     """
    
#     if not style_path.exists():
#         logger.error("Unable to file the pdf_style.md. Generating pdf without style.")
#         return
        
#     style_data_in_bytes = style_path.read_bytes()

#     with tempfile.NamedTemporaryFile(
#         mode="wb",
#         delete=False,
#         dir=model_response_filepath.parent,
#     ) as tmp:
#         tmp_path = Path(tmp.name)

#         tmp.write(style_data_in_bytes)
        
#         shutil.copyfileobj(model_response_filepath.open("rb"), tmp)

#     tmp_path.replace(model_response_filepath)
#     logger.info("Added style to the front of the model response.")


def save_model_response(model_response_path: Path, input_pdf_name: str) -> Path:
    """
    Takes the _model_response.md or a markdown file and converts it into pdf.  
    Args:
        model_response_path (Path): Path to the markdown file write by the model.
        input_pdf_name (str): Name of the input pdf.

    Returns:
        Path: Path to the generated pdf
    """
    if shutil.which("tectonic") is None:
        logger.critical("tectonic.exe is not available in system paths.")
        # sys.exit("tectonic.exe is not available in system paths.")
        raise ValueError("tectonic.exe is not available in system paths.")
    
    
    
    temp_path = model_response_path.resolve().parent
    
    output_path = temp_path / f'{input_pdf_name}(make_sense).pdf'
    
    args = [
        "pandoc",
        "-f", "markdown",
        "-t", "pdf",
        "--pdf-engine=tectonic",
        f"--resource-path={str(temp_path  / 'Images')}",
        "-s",
        "-o", str(output_path),
        str(model_response_path),
    ]

    try:
        subprocess.run(args, check=True, timeout=180)
        
    except FileNotFoundError as e:
        logger.critical("Required executable was not found: %s", e.filename)
        # sys.exit(str(e))
        raise FileNotFoundError(f"Required executable was not found: {e.filename}")
    
    except subprocess.TimeoutExpired:
        logger.critical("Markdown to PDF conversion timed out.")
        raise TimeoutError("Markdown to PDF conversion timed out.")
        # sys.exit("Markdown to PDF conversion timed out.")
    
    except subprocess.CalledProcessError as e:
        logger.critical("Error converting markdown to PDF: %s", e)
        raise 
        # sys.exit(f"Error converting markdown to PDF: {e}")
    
    logger.info("Succefully created the pdf for %s", str(model_response_path))
    
    return output_path

if __name__ == '__main__':
    
    if len(sys.argv) != 2:
        sys.exit('Expecting a markdown file to convert')
    
    markdown_filepath = sys.argv[1]
    
    markdown_filepath = Path(markdown_filepath + '.md').resolve() if not markdown_filepath.endswith('.md') else Path(markdown_filepath).resolve()

    save_model_response(markdown_filepath, 'user')