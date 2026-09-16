"""
This module call's models with a fallback.

EXPECTED FILES & VARIABLES: .env

INPUT: Temp/markdown.md

OUTPUT: Temp/model_response.pdf
"""

from pathlib import Path
import requests
import logging
import sys
import os
import configparser

logger = logging.getLogger('make_sense.model')

def _call_model(model:str, messages:list, api_key:str) -> requests.Response:
    """
    Sends post request to the given model and retuns the response.
    Args:
        model (str): model slug from openrouter
        messages (list): prompt for the model
        api_key (str): openrouter api key

    Returns:
        requests.Response: Endpoint's raw response with model's response inside.
    """
    
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": model, "messages": messages, "stream": False, "reasoning": {"enabled": True}},
        timeout=30,
    )
    
    return response

def _get_safe_response(messages: list, models: list, api_key: str) -> str:
    """
    Make requests to the primary model, then a fallback model if something goes wrong.
    Args:
        messages (list): prompt for the model.
        models (list): model to use with fallbacks. First model considered as primary.
        api_key (str): openrouter api key.

    Raises:
        RuntimeError: If both models failed to generate response.

    Returns:
        response (str): model's response. 
    """
    
    for model in models:
        try:
            response = _call_model(model, messages, api_key)

            if response.status_code == 429:
                print(f"{model} rate limited, trying next model...")
                continue

            if response.status_code >= 500:
                print(f"{model} server error, trying next model...")
                continue

            response.raise_for_status()
            response_dict = response.json()
            
            model_response = response_dict['choices'][0]['message']['content']
            
            if not model_response:
                logger.error("%s responded with empty string, trying next model...", model)
                continue
            
            return model_response
            
        except requests.exceptions.Timeout:
            logger.error("%s timed out, trying next model...", model)
            continue
        except requests.exceptions.RequestException as e:
            logger.error("%s failed: %s, trying next model...", model, str(e))
            continue

    raise RuntimeError("All models failed to run.")


def generate_explanation(md_filepath: Path, api_key: str) -> Path:
    """
    Reads processed markdown file, generates explanation, write's the resulting response markdown file in the same folder.
    
    Expected files: 
        The code assumes prompt.txt is inside the project root.
    Args:
        md_filepath (Path): Processed markdown file from marker.
        api_key (Path): openrouter API key.
    
    Output:
        The path to the saved model's response file.
    """
    
    
    additional_prompt = """
<START OF PAPER>

{md_content}

<END OF PAPER>"""

    if not api_key:
        logger.critical('Recieved an empty openrouter api key')
        sys.exit('Recieved an empty openrouter api key')
    
    output_filepath = md_filepath.parent / f'{md_filepath.stem}_model_response.md'
    project_root = md_filepath.parents[1]
    
    try:
        with open(md_filepath, 'r', encoding='utf-8') as marker_output:
            data = marker_output.read()
            try:
                with open(project_root / 'prompt.txt', 'r', encoding='utf-8') as prompt_file:
                    prompt = prompt_file.read()
                    
                    messages = [{
                        'role':'user',
                        "content": prompt + additional_prompt.format(md_content=data)
                    }]
                    
                    
                    try:
                        parser = configparser.ConfigParser()
                        parser.read(project_root / 'project_variables.ini')
                        
                        models = list(parser['MODELS'].values())
                        
                        model_response = _get_safe_response(messages=messages, models = models, api_key=api_key)
                    
                    except KeyError as e:
                        logger.critical(f"Unable to find project_variables.ini in project root.")
                        sys.exit(str(e))
                    
                    try:
                        with open(output_filepath, 'w', encoding='utf-8') as response_file:
                            response_file.write(model_response)
                            
                    except Exception as e:
                        logger.critical("Model responded succesfully, But failed to save the response: %s", str(e))
                        sys.exit(str(e))
                    
                    return output_filepath
                    
            except FileNotFoundError as e:
                logger.critical("Unable to find the prompt.txt inside %s", str(project_root))
                sys.exit(str(e))
            
    except FileNotFoundError as e:
        logger.critical("Unable to find the marker's output file at %s", str(md_filepath))
        sys.exit(str(e))

if __name__ == '__main__':
    
    project_root = Path(__name__).resolve().parents[2]
    
    try:
        api_key = os.environ['OPENROUTER_API_KEY']
        
    except KeyError as e:
        logging.critical("Couldn't find OPENROUTER_API_KEY in Environment variables")
        sys.exit()
    
    if len(sys.argv) != 2:
        sys.exit('Expecting a path for the markdown to start.')
    
    md_filepath = sys.argv[1]
    
    if not md_filepath.endswith('.md'):
        md_filepath += '.md'
    
    md_filepath = Path(md_filepath).resolve()
    
    generate_explanation(md_filepath, api_key)