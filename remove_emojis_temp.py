import os
import re

emoji_map = {
    '✅': '[SUCCESS]',
    '⚠️': '[WARNING]',
    '🚨': '[CRITICAL]',
    'ℹ️': '[INFO]',
    '📊': '[DATA]',
    '📈': '[TREND UP]',
    '📉': '[TREND DOWN]',
    '💰': '[FINANCE]',
    '🧠': '[AI]',
    '🧪': '[TEST]',
    '🚀': '[LAUNCH]',
    '🔍': '[SEARCH]',
    '🕵️': '[AGENT]',
    '🚧': '[BUILD]',
    '⚖️': '[BALANCE]',
    '🩸': '[PAIN]',
    '📚': '[EVIDENCE]',
    '😤': '[VALIDATE]',
    '📏': '[MEASURE]',
    '📝': '[REPORT]',
    '💪': '[STRENGTH]',
    '💻': '[TECH]',
    '🌍': '[GLOBAL]',
    '🧮': '[CALCULATE]',
    '💡': '[IDEA]',
    '📂': '[FILE]',
    '🏆': '[SCORE]',
    '💭': '[THINK]',
    '✨': '[MAGIC]',
    '👀': '[OBSERVE]',
    '🏗️': '[STRUCTURE]',
    '📄': '[DOC]',
    '💾': '[SAVE]',
    '🕵️‍♂️': '[AGENT]',
    '🕵️‍♀️': '[AGENT]',
    '👉': '[STEP]',
    '⏳': '[WAIT]',
    '📱': '[MOBILE]',
    '🎉': '[CELEBRATE]',
    '🎯': '[TARGET]',
    '🔥': '[FIRE]',
    '🔴': '[ERROR]',
    '🛠️': '[TOOLS]',
    '💰': '[MONEY]'
}

directories = [
    r"c:\Users\mariam\OneDrive\Desktop\vs code\Grad project\Spark2Scale-AI\app\graph\market_research_agent",
    r"c:\Users\mariam\OneDrive\Desktop\vs code\Grad project\Spark2Scale-AI"
]

files_to_check = [
    r"c:\Users\mariam\OneDrive\Desktop\vs code\Grad project\Spark2Scale-AI\verify_market_research_agent.py",
]

files_changed = 0

# Check specific files
for filepath in files_to_check:
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            new_content = content
            for emoji, tag in emoji_map.items():
                new_content = new_content.replace(emoji, tag)
            
            if new_content != content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"Updated {filepath}")
                files_changed += 1
        except Exception as e:
            print(f"Error processing {filepath}: {e}")

# Check directories
for directory in directories[:1]: # just market_research_agent first
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    new_content = content
                    for emoji, tag in emoji_map.items():
                        new_content = new_content.replace(emoji, tag)
                    
                    if new_content != content:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        print(f"Updated {filepath}")
                        files_changed += 1
                except Exception as e:
                    print(f"Error processing {filepath}: {e}")

print(f"Total files updated: {files_changed}")
