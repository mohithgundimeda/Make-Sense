"""
Entry Point for the project. Takes a pdf, parses it to .md file, generates a detailed explanation, saves it as a pdf.

EXPECTED FILES & VARIABLES: logging_config.json, marker_config.json, LLAMA_CPP_BINARY and SURYA_INFERENCE_BACKEND in OS's environement variables.

INPUT: The path for .pdf file

OUTPUT : Resulted .pdf file is saved in Temp folder.
"""
import sys
import json
import logging
import logging.config
import os
from pathlib import Path
from make_sense.parser import MarkerSettings, pdf_2_md
from make_sense.model import generate_explanation
from make_sense.pandoc import save_model_response

def setup_logging(config_path: str = "logging_config.json") -> None:
    """
    Sets up root logger basic config and some logging parameters from logging_config.json. If file missing, defaults to 
    logging.INFO level with console loging.
    Args:
        config_path (str, optional): path to the json configuration file. Defaults to "logging_config.json".
    """
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    
    except FileNotFoundError:
        
        logging.basicConfig(level=logging.INFO)
        logging.error(f"Configuration file {config_path} not found. Using basic config.")


if __name__ == '__main__':
    
    setup_logging()
    
    logger = logging.getLogger('make_sense')
    
    project_root = Path(__name__).resolve().parent
    
    temp_path = project_root / 'Temp'
    
    temp_path.mkdir(exist_ok=True)
    
    # Validate the given input
    
    if len(sys.argv) != 2:
        sys.exit("Expecting the pdf's path.")
    
    str_pdf_filename = sys.argv[1].strip().replace(" ", '_')
        
    # Assuming the file is already inside Temp folder (raises error if it doesn't)
    pdf_filepath = (temp_path / (str_pdf_filename + '.pdf')) if not str_pdf_filename.endswith('.pdf') else (temp_path / str_pdf_filename)
    
    if not pdf_filepath.is_file():
        resolved_pdf_filepath = str(pdf_filepath)
        logger.critical("Can't find the given pdf file %s", resolved_pdf_filepath)
        sys.exit(f"Can't find the given pdf file {resolved_pdf_filepath}")
    
    marker_config_path = project_root / 'marker_config.json'
    
    try:
        with open(marker_config_path, 'r', encoding='utf-8') as jfile:
            config = json.load(jfile)

            settings = MarkerSettings(**config)
            
            marker_output_path = pdf_2_md(settings.model_dump(), pdf_filepath)

            model_response_path = generate_explanation( marker_output_path, os.environ.get('OPENROUTER_API_KEY', '') )
            
            output_pdf_path = save_model_response(model_response_path, pdf_filepath.stem)
            
    
    except FileNotFoundError as e:
        logger.critical("Unable to find %s", str(marker_config_path))
        sys.exit(str(e))
    
    else:
        logger.info(f'Task Completed for {str(pdf_filepath)}.')
    
    
    # Delete the copied .pdf file after generating output.pdf