#
# Copyright 2016 The BigDL Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import torch
import time
import argparse

from transformers import AutoModelForCausalLM, AutoTokenizer
from ipex_llm import optimize_model

# you could tune the prompt based on your own model,
# here the prompt tuning refers to https://huggingface.co/stabilityai/stablelm-zephyr-3b#usage
STABLELM_PROMPT_FORMAT = """<|user|>
{prompt} <|endoftext|>
<|assistant|>"""

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Predict Tokens using `generate()` API for StableLM model')
    parser.add_argument('--repo-id-or-model-path', type=str, default="stabilityai/stablelm-zephyr-3b",
                        help='The huggingface repo id for the StableLM (e.g. `stabilityai/stablelm-zephyr-3b`) to be downloaded'
                             ', or the path to the huggingface checkpoint folder')
    parser.add_argument('--prompt', type=str, default="What is AI?",
                        help='Prompt to infer')
    parser.add_argument('--n-predict', type=int, default=32,
                        help='Max tokens to predict')

    args = parser.parse_args()
    model_path = args.repo_id_or_model_path

    # Load model
    model = AutoModelForCausalLM.from_pretrained(model_path,
                                                 trust_remote_code=True,
                                                 torch_dtype='auto',
                                                 low_cpu_mem_usage=True)
    
    # With only one line to enable IPEX-LLM optimization on model
    # When running LLMs on Intel iGPUs for Windows users, we recommend setting `cpu_embedding=True` in the optimize_model function.
    # This will allow the memory-intensive embedding layer to utilize the CPU instead of iGPU.
    model = optimize_model(model)

    model = model.to('xpu')

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    
    # Generate predicted tokens
    with torch.inference_mode():
        prompt = STABLELM_PROMPT_FORMAT.format(prompt=args.prompt)
        input_ids = tokenizer.encode(prompt, return_tensors="pt").to('xpu')
        # ipex_llm model needs a warmup, then inference time can be accurate
        output = model.generate(input_ids,
                                max_new_tokens=args.n_predict)

        # start inference
        st = time.time()
        # if your selected model is capable of utilizing previous key/value attentions
        # to enhance decoding speed, but has `"use_cache": false` in its model config,
        # it is important to set `use_cache=True` explicitly in the `generate` function
        # to obtain optimal performance with IPEX-LLM INT4 optimizations
        output = model.generate(input_ids,
                                max_new_tokens=args.n_predict)
        torch.xpu.synchronize()
        end = time.time()
        output = output.cpu()
        output_str = tokenizer.decode(output[0], skip_special_tokens=True)
        print(f'Inference time: {end-st} s')
        print('-'*20, 'Output', '-'*20)
        print(output_str)