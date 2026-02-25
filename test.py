from dotenv import load_dotenv
import os
load_dotenv()
print('MONDAY:', repr(os.getenv('MONDAY_API_KEY')))
print('OPENAI:', repr(os.getenv('OPENAI_API_KEY')))