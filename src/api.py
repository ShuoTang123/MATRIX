import requests
from concurrent.futures import ThreadPoolExecutor
MAX_WORKERS = 10
import random
from src.utils import wizard_vicuna_template, mistral_template
from src.utils import call_gpt


"""
The urls for open-source models
"""
model_urls = \
{
    "wizard-vicuna-7b": [
        'http://192.168.28.140:8083',
    ],
    "mistral-7b-instruct": [
        'http://192.168.28.140:8080',
        'http://192.168.28.140:8081',
        'http://192.168.28.140:8082'
    ]
}


"""
chat template used for different models
"""
chat_template = \
{
    
    'wizard-vicuna-7b':wizard_vicuna_template,
    'mistral-7b-instruct':mistral_template
}



def chatcompletion(prompt:str, max_tokens=1024, temperature=0.2, model='vicuna-7b', index=0) -> str:

    if model not in model_urls.keys():
        print(f"Unsupported model {model}, call openai api instead")
        return call_gpt(model=model, prompt=prompt)


    prompt_with_template = chat_template[model](prompt)

    url_list = model_urls[model]
    curr_url = url_list[index]

    """call vllm model api server"""

    url = f"{curr_url}/generate"
    payload = {
        "prompt": prompt_with_template,
        "temperature": temperature,
        "stream": False,
        "top_p": 1.0,
        "max_tokens": max_tokens,
        "logprobs": 5
    }
    response = requests.post(url, json=payload)
    
    return response.json()['text'][0].replace(prompt_with_template, '')


if __name__ == '__main__':
    question = 'How to learn math well?'
    model = 'wizard-vicuna-7b'
    batch_question = [question for i in range(MAX_WORKERS)]

    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [
                executor.submit(chatcompletion, question, model=model) for question in batch_question
            ]
    output = [future.result() for future in futures]
    
   