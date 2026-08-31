import os
import glob
import requests

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def audit_and_improve_repo():
    if not GROQ_API_KEY:
        print("Error: GROQ_API_KEY is missing.")
        return

    python_files = glob.glob("**/*.py", recursive=True)
    
    for file_path in python_files:
        if file_path == "auto_auditor.py":
            continue
            
        print(f"Upgrading: {file_path}...")
        with open(file_path, "r", encoding="utf-8") as f:
            code_content = f.read()

        prompt = f"""
        You are an elite senior quantitative developer. Fix all bugs, syntax errors, and optimize this Python code for algorithmic trading and market signals.
        Return ONLY the fully corrected, production-ready Python code without any explanations or markdown wrappers.

        Code:
        {code_content}
        """

        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "llama3-70b-8192",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }

        try:
            response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=60)
            res_json = response.json()
            improved_code = res_json['choices'][0]['message']['content'].replace("```python", "").replace("```", "").strip()
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(improved_code)
            print(f"Successfully upgraded: {file_path}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    audit_and_improve_repo()
