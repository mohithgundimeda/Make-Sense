"""
Utilises marker-pdf to parse a given pdf and saves .md, images(Images folder) as input pdf's siblings, in the same folder.

EXPECTED FILES & Variables: input pdf's path, marker_config.json, .env, LLAMA_CPP_BINARY and SURYA_INFERENCE_BACKEND in OS's environement variables

INPUT: Temp/user_file.pdf

ASSUMPTION(For make_sense project): The pdf file is inside Temp folder.

OUTPUT: Temp/user_file.pdf, Temp/user_file.md, Temp/Images/*
"""

from __future__ import annotations
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

## Choosing llama.cpp over vLLM to run the model in Marker, It MUST be set in environment variables before any marker/surya import
os.environ["SURYA_INFERENCE_BACKEND"] = "llamacpp" # remove in prod
os.environ["LLAMA_CPP_BINARY"] = str(PROJECT_ROOT / 'llamacpp' / 'llama-server') # remove in prod

if (not os.environ.get("LLAMA_CPP_BINARY") or 
    not os.environ.get("SURYA_INFERENCE_BACKEND")):
    
    raise ValueError('Missing llama.cpp environment variables (SURYA_INFERENCE_BACKEND, LLAMA_CPP_BINARY).')

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import logging
import json
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.config.parser import ConfigParser


logger = logging.getLogger('make_sense.parser')

class MarkerSettings(BaseSettings):
    """Environment-driven configuration for the Marker conversion step."""
    
    llm_service: str 
    mode: str
    output_format: str
    use_llm: bool
    gemini_model_name: str
    force_ocr: bool 
    redo_inline_math: bool
    max_retries: int
    retry_wait_time: int
    timeout: int
    
    gemini_api_key: str = Field(validation_alias='GEMINI_API_KEY')
    
    model_config = SettingsConfigDict(
        env_file = PROJECT_ROOT / '.env',
        env_file_encoding= 'utf-8',
        extra='ignore'
        )


def pdf_2_md(config: dict, pdf_filepath: Path) -> None:
    """Takes PDF and generate marker_output.md, image in output_dir

    Args:
        config (dict): Configurations for Marker.
        pdf_filepath (Path): Absolute path to the pdf file.
    """
    
    
    if not pdf_filepath.exists():
        logger.critical("pdf_2_md() couldn't able to find the user's input file %s.", str(pdf_filepath))
        raise FileNotFoundError(f"Couldn't found {pdf_filepath.name}")
    
    config_parser = ConfigParser(config)
    
    try:
        converter = PdfConverter(
                        config=config_parser.generate_config_dict(),
                        artifact_dict=create_model_dict(),
                        processor_list=config_parser.get_processors(),
                        renderer=config_parser.get_renderer(),
                        llm_service=config_parser.get_llm_service()
                    )

        
        rendered_output = converter(str(pdf_filepath))
        
        output_filepath = pdf_filepath.parent / f'{pdf_filepath.stem}.md'
        
        try:
            with open(output_filepath, 'w', encoding='utf-8') as md_file:
                md_file.write(rendered_output.markdown)
        except Exception as e:
            logger.critical("Conversion process completed, but error writing markdown to output file %s.", str(output_filepath))
            sys.exit(str(e))
        else:
             logger.info('Marker succesfully converted %s to %s.md', pdf_filepath.name, pdf_filepath.stem)
            
        
        images_path = pdf_filepath.parent / 'Images'
        images_path.mkdir(exist_ok=True)
        
        images = rendered_output.images
        
        if images:
            logger.info('Found %d images in %s.pdf', len(images), pdf_filepath.name)
            for img_name, img_obj in images.items():
                
                try:
                    img_obj.save(images_path / f'{img_name}')
                except Exception as e:
                    logger.error('Failed to save %s in %s', img_name, str(images_path))
        
                
    except Exception as e:
        logger.critical("Marker couldn't convert the pdf %s to markerdown. Check the console for more details.", str(pdf_filepath))
        sys.exit(str(e))
    
        
        
if __name__ == "__main__":
    
    
    if len(sys.argv) != 2:
        sys.exit('Expecting a path for the pdf to start.')
    
    pdf_filepath = sys.argv[1]
    
    if not pdf_filepath.endswith('.pdf'):
        pdf_filepath += '.pdf'
    
    try:
        with open(PROJECT_ROOT / 'marker_config.json', 'r', encoding='utf-8') as jfile:
            config = json.load(jfile)

            settings = MarkerSettings(**config)
            
            pdf_2_md(settings.model_dump(), Path(pdf_filepath).resolve())
    
    except FileNotFoundError as e:
        sys.exit(str(e))