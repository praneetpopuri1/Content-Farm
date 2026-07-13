import re
import subprocess
import os
import platform
from jinja2 import StrictUndefined, Template
from litellm import completion
from exceptions import FormatError, InterruptAgentFlow, LimitsExceeded, Submitted, TimeExceeded
import traceback

def query_lm(messages: list[dict[str, str]]) -> str:
    response = completion(
        model="gemini/gemini-3.5-flash",
        messages=messages,
        max_tokens=8192,
    )
    return response.choices[0].message.content or ""

FORMAT_ERROR_TEMPLATE = """Please always provide EXACTLY ONE action in triple backticks, found {n} actions.

If you want to end the task, please issue the following command: `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`
without any other command.
Else, please format your response exactly as follows:

THOUGHT: Your reasoning and analysis here. Explain why you want to perform the action.

```mswea_bash_command
your_command_here
```"""

def parse_action(lm_output: str) -> str:
    """Take LM output, return action. Raises FormatError unless exactly one action is found."""
    matches = re.findall(
        r"```(?:mswea_bash_command|bash-action)\s*\n(.*?)\n```",
        lm_output,
        re.DOTALL
    )
    if len(matches) == 1:
        return matches[0].strip()
    raise FormatError({
        "role": "user",
        "content": FORMAT_ERROR_TEMPLATE.format(n=len(matches)),
    })

def execute_action(command: str) -> dict:
    """Execute action, return output and return code"""
    result = subprocess.run(
        command,
        shell=True,
        text=True,
        env=os.environ,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    return {"output": result.stdout, "returncode": result.returncode}

INSTANCE_TEMPLATE = """Please solve this issue: {{task}}

You can execute bash commands and edit files to implement the necessary changes.

## Recommended Workflow

This workflow should be done step-by-step so that you can iterate on your changes and any possible problems.

1. Analyze the codebase by finding and reading relevant files
2. Create a script to reproduce the issue
3. Edit the source code to resolve the issue
4. Verify your fix works by running your script again
5. Test edge cases to ensure your fix is robust
6. Submit your changes and finish your work by issuing the following command: `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`.
   Do not combine it with any other command. <important>After this command, you cannot continue working on this task.</important>

## Important Rules

1. Every response must contain exactly one action
2. The action must be enclosed in triple backticks
3. Directory or environment variable changes are not persistent. Every action is executed in a new subshell.
   However, you can prefix any action with `MY_ENV_VAR=MY_VALUE cd /path/to/working/dir && ...` or write/load environment variables from files

<system_information>
{{system}} {{release}} {{version}} {{machine}}
</system_information>

## Formatting your response

Here is an example of a correct response:

<example_response>
THOUGHT: I need to understand the structure of the repository first. Let me check what files are in the current directory to get a better understanding of the codebase.

```mswea_bash_command
ls -la
```
</example_response>

## Useful command examples

### Create a new file:

```mswea_bash_command
cat <<'EOF' > newfile.py
import numpy as np
hello = "world"
print(hello)
EOF
```

### Edit files with sed:

{%- if system == "Darwin" -%}
<important>
You are on MacOS. For all the below examples, you need to use `sed -i ''` instead of `sed -i`.
</important>
{%- endif -%}

```mswea_bash_command
# Replace all occurrences
sed -i 's/old_string/new_string/g' filename.py

# Replace only first occurrence
sed -i 's/old_string/new_string/' filename.py

# Replace first occurrence on line 1
sed -i '1s/old_string/new_string/' filename.py

# Replace all occurrences in lines 1-10
sed -i '1,10s/old_string/new_string/g' filename.py
```

### View file content:

```mswea_bash_command
# View specific lines with numbers
nl -ba filename.py | sed -n '10,20p'
```

### Any other command you want to run

```mswea_bash_command
anything
```
"""

def render_template(template: str, **kwargs) -> str:
    """Render a Jinja2 template with platform info plus any extra variables."""
    return Template(template, undefined=StrictUndefined).render(
        **kwargs, **platform.uname()._asdict()
    )

def has_finished(output: str):
    """Raise Submitted if the agent issued the submit command."""
    lines = output.lstrip().splitlines(keepends=True)
    if lines and lines[0].strip() == "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT":
        submission = "".join(lines[1:])
        raise Submitted({
            "role": "exit",
            "content": submission,
            "extra": {"exit_status": "Submitted", "submission": submission},
        })

# Main agent loop
task = "create basic website talking about interesting cowboy facts inside my Documents directory"
messages = [{
    "role": "system",
    "content": """You are a helpful assistant that can interact with a computer.

    Your response must contain exactly ONE bash code block with ONE command (or commands connected with && or ||).
    Include a THOUGHT section before your command where you explain your reasoning process.
    Format your response as shown in <format_example>.

    <format_example>
    Your reasoning and analysis here. Explain why you want to perform the action.

    ```mswea_bash_command
    your_command_here
    ```
    </format_example>

    Failure to follow these rules will cause your response to be rejected."""
}, {
    "role": "user",
    "content": render_template(INSTANCE_TEMPLATE, task=task)
}]
def handle_uncaught_exception(e: Exception) -> None:
    messages.append({
        "role": "exit",
        "content": str(e),
        "extra": {
            "exit_status": type(e).__name__,
            "submission": "",
            "exception_str": str(e),
            "traceback": traceback.format_exc(),
        },
    })

n_consecutive_format_errors = 0 
max_consecutive_format_errors = 3
while True:
    try:
        lm_output = query_lm(messages)
        print("LM output", lm_output)
        messages.append({"role": "assistant", "content": lm_output})  # remember what the LM said
        action = parse_action(lm_output)  # separate the action from output
        print("Action", action)
        if action == "exit":
            break
        result = execute_action(action)
        print("Output", result["output"])
        has_finished(result["output"])  # raises Submitted (ends the loop) on the submit command
        observation = f"<returncode>{result['returncode']}</returncode>\n<output>\n{result['output']}</output>"
        messages.append({"role": "user", "content": observation})  # send command output back
        n_consecutive_format_errors = 0
    except FormatError as e:
        n_consecutive_format_errors += 1
        if 0 < max_consecutive_format_errors <= n_consecutive_format_errors:
            messages.extend([
                *e.messages,
                {
                    "role": "exit",
                    "content": "RepeatedFormatError",
                    "extra": {"exit_status": "RepeatedFormatError", "submission": ""},
                },
            ])
            break
        else:
            messages.extend(e.messages)
    except InterruptAgentFlow as e:
        messages.extend(e.messages)
        break
    except Exception as e:
        handle_uncaught_exception(e)
        raise