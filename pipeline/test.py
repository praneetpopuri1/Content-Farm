from google import genai
from google.genai import types
import base64
import time
from pathlib import Path
import json

import subprocess
import prompts_and_schema
import numpy as np
directory = Path("../inputs/chunks_15min")

file_paths = [str(p) for p in directory.iterdir() if p.is_file()]
print(file_paths)
