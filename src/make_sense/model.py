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
from google.genai import Client, types
import pydantic
from pydantic import BaseModel

logger = logging.getLogger('make_sense.model')

class ResponseStructure(BaseModel):
        """
        Intended Structure for model's response.
        Args:
            BaseModel : Pydantic Base Class
        """
        title : str
        response: str
        

model_response = """
---
title: "{title}"
documentclass: scrartcl
geometry:
- margin=1in
fontfamily: tgtermes
fontsize: 11pt
toc: true
toc-depth: 2
colorlinks: true
linkcolor: blue
---

{response}
"""


import re

def _extract_title_and_body(raw_text: str) -> tuple[str, str]:
    """
    Seperates title and explanation from model's response.
    Args:
        raw_text (str): model's response

    Returns:
        tuple[str, str]: _description_
    """
    if not raw_text:
        raise ValueError("Received empty input.")
    
    match = re.match(r'^#{1,6}\s+(.+?)\n(.*)', raw_text.strip(), re.DOTALL)
    
    if match:
        title = match.group(1).strip()
        body = match.group(2).strip()
        return title, body

    return "Untitled", raw_text

def _call_gemini(data: str, prompt: str, model:str) -> str:
    """
    Fallback function to call gemini, if openrouter models were unsuccessfull.
    Args:
        data (str): parsed markdown file from pdf.
        prompt (str): Prompt from prompt.txt
        model (str): gemini model version to use.

    Raises:
        ValueError: When there is no response.
        RuntimeError: When gemini isn't accessable.

    Returns:
        str: gemini response.
    """
    
    contents = types.Content(
        role='user',
        parts=[types.Part.from_text(text=data)]
    )
    
    try:
        with Client(http_options=types.HttpOptions(api_version='v1alpha')) as client:
            response = client.models.generate_content(
                model=model,
                contents=[contents],
                config=types.GenerateContentConfig(
                    system_instruction=prompt,
                    thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
                    max_output_tokens=30000,
                    response_mime_type='application/json',
                    response_json_schema=ResponseStructure.model_json_schema(),
                )
            )
            
            response_structure = response.parsed

            if not isinstance(response_structure, dict):
                logger.critical(f"Expected Dict from {model}, got {type(response_structure)}")
                raise TypeError(f"Expected dict, got {type(response_structure)}")

            logger.info("{model} responded successfully with json schema.")
            
            parsed = ResponseStructure.model_validate(response_structure)

            return model_response.format(
                title=parsed.title,
                response=parsed.response,
            )
            
    except Exception as e:
        logger.critical("Error during accessing gemini: %s", str(e))
        raise RuntimeError(f"Error during accessing gemini: {str(e)}")


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
        json={
        "model": model,
        "messages": messages,
        "stream": False,
        "reasoning": {"enabled": True},
        },
        timeout=180,
    )
    
    return response

def _get_safe_response(models: list, api_key: str, prompt: str, data: str, gemini_model:str) -> str:
    """
    Make requests to the primary model, then a fallback model if something goes wrong.
    Args:
        models (list[str]): openrouter model to use with fallbacks. First model considered as primary.
        api_key (str): openrouter api key.
        prompt (str): Prompt from prompt.txt
        data (str): parsed markdown file from pdf.
        gemini_model (str): gemini model version to use.

    Raises:
        RuntimeError: If both models failed to generate response.

    Returns:
        response (str): model's response. 
    """
    messages = [
                {'role':'user',"content": data},
                {"role": "system", "content": prompt}
                ]
    
    for model in models:
        try:
            response = _call_model(model, messages, api_key)
            
            if response.status_code == 429:
                logger.error(f"{model} rate limited, trying next model...")
                continue

            if response.status_code >= 500:
                logger.error(f"{model} server error, trying next model...")
                continue

            response.raise_for_status()
            
            
            response_dict = response.json()
            try:
                response_dict = response.json()

                if "error" in response_dict:
                    error_info = response_dict["error"]
                    logger.error("%s returned an error object: %s. Trying next model...", model, error_info)
                    continue

                try:
                    raw_text = response_dict['choices'][0]['message']['content']
                except (KeyError, IndexError) as e:
                    logger.error("%s returned unexpected response shape: %s | full response: %s. Trying next model...", model, str(e), response_dict)
                    continue
                
                if not raw_text:
                    logger.error("%s returned empty response. Trying next model...", model)
                    continue
                
                title, content = _extract_title_and_body(raw_text)
                
                logger.info("%s generated response successfully.", model)
                
                
                return model_response.format(title=title, response=content)
            
            except pydantic.ValidationError as e:
                logger.error("Error from %s, during validating the response json: %s. Trying next model..", model, str(e))
                continue
            
        except requests.exceptions.Timeout:
            logger.error("%s timed out, trying next model...", model)
            continue
        
        except requests.exceptions.ConnectionError:
            logger.error("Unable to connect to openrouter. Trying next model..")
            continue
        
        except requests.exceptions.RequestException as e:
             body = getattr(e.response, "text", "no response body")
             logger.error("%s failed: %s | response: %s. Trying next model...", model, str(e), body)
             continue

    
    
    try:
        logger.info(f"Error trying openrouter models, trying {gemini_model}.")
        gemini_response = _call_gemini(data=data, prompt=prompt, model=gemini_model)
        return gemini_response
    
    except Exception:
        pass
    
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

    if not api_key:
        logger.critical('Recieved an empty openrouter api key')
        raise ValueError(f"Recieved an empty openrouter api key")
        # sys.exit('Recieved an empty openrouter api key')
    
    output_filepath = md_filepath.parent / f'{md_filepath.stem}_model_response.md'
    project_root = md_filepath.parents[1]
    
    try:
        with md_filepath.open('r', encoding='utf-8') as marker_output:
            
            data = marker_output.read()
            try:
                
                with project_root.joinpath('prompt.txt').open( 'r', encoding='utf-8') as prompt_file:
                    prompt = prompt_file.read()
                    
                    try:
                        parser = configparser.ConfigParser()
                        parser.read(project_root / 'project_variables.ini')
                        
                        try:
                            openrouter_models = list(parser['OPENROUTER'].values())
                            gemini_model = list(parser['GEMINI'].values())[0]
                        
                        except KeyError as e:
                            logger.critical("Unable to find project_variables.ini in project root.")
                            raise
                        
                        model_response = _get_safe_response(models = openrouter_models, api_key=api_key, prompt=prompt, data = data, gemini_model=gemini_model)
                        
                    
                    except Exception as e:
                        logger.critical(f"Model faild to give response. Note somtimes the api response is not having 'choices' field.")
                        raise
                        # sys.exit(str(e))
                    
                    try:
                        output_filepath.open('w', encoding='utf-8').write(model_response)
                        logger.info("Response wrote to %s", str(output_filepath))
                            
                    except Exception as e:
                        logger.critical("Model responded succesfully, But failed to save the response: %s", str(e))
                        raise
                        # sys.exit(str(e))
                    
                    return output_filepath
                    
            except FileNotFoundError as e:
                logger.critical("Unable to find the prompt.txt inside %s", str(project_root))
                raise
                # sys.exit(str(e))
            
    except FileNotFoundError as e:
        logger.critical("Unable to find the marker's output file at %s", str(md_filepath))
        raise
        # sys.exit(str(e))

if __name__ == '__main__':
    
    try:
        api_key = os.environ['OPENROUTER_API_KEY']
        
    except KeyError as e:
        logger.critical("Couldn't find OPENROUTER_API_KEY in Environment variables")
        sys.exit()
    
    if len(sys.argv) != 2:
        sys.exit('Expecting a path for the markdown to start.')
    
    md_filepath = sys.argv[1]
    
    if not md_filepath.endswith('.md'):
        md_filepath += '.md'
    
    md_filepath = Path(md_filepath).resolve()
    
    generate_explanation(md_filepath, api_key)