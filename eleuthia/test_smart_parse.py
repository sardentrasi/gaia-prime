import re

# Simulation Data
# Assume 'ithaldin@myhaldin.com' is NOT in accounts list initially, or has different case?
mock_accounts = [
    {'name': 'Work', 'username': 'fajar@haldin-natural.com'},
    {'name': 'Secret', 'username': 'admin@secret.com'}
]

def find_account(search_term):
    st = search_term.lower()
    if st == 'work': return 'Work'
    if st == 'personal': return 'Personal'
    for acc in mock_accounts:
        if st in acc['username'].lower():
            return acc['name']
    return None

# User Input
raw_args = "ithaldin@myhaldin.com fajar.arif@haldin-natural.com tolong kirim laporan"
print(f"Input: '{raw_args}'")

# --- Logic from chat engine (smart parsing) ---

# 1. Parse FROM (Explicit keyword check first)
from_email_match = re.search(r'(?:from|dari)\s+([\w\.-]+@[\w\.-]+\.\w+|work|personal)', raw_args, re.IGNORECASE)
from_account = None

clean_args = raw_args

if from_email_match:
    from_target = from_email_match.group(1)
    from_account = find_account(from_target)
    clean_args = clean_args.replace(from_email_match.group(0), '')
    print(f"DEBUG: Explicit 'from' found: {from_target} -> {from_account}")

# 2. Extract All Emails for Smart Parsing
all_emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', clean_args)
to_email = None

# Smart Logic: Identify Sender vs Recipient from list
remaining_emails = []
for em in all_emails:
    if not from_account:
        possible_sender = find_account(em)
        if possible_sender:
            from_account = possible_sender
            print(f"DEBUG: Smart Sender detected: {em} -> {from_account}")
            continue 
    remaining_emails.append(em)
    
# Check first token
first_token = clean_args.strip().split()[0].lower() if clean_args.strip() else ""
if not from_account and first_token in ('work', 'personal'):
     from_account = find_account(first_token)
     clean_args = re.sub(r'^\s*'+first_token, '', clean_args, count=1, flags=re.IGNORECASE)
     print(f"DEBUG: Keyword Sender detected: {first_token} -> {from_account}")

# Now determine TO email
if remaining_emails:
    to_email = remaining_emails[0]
    print(f"DEBUG: Recipient detected: {to_email}")
else:
     print(f"DEBUG: No recipient found. All emails: {all_emails}, From: {from_account}")
     exit()

# 3. Clean up Instruction
clean_args = clean_args.replace(to_email, '')

for w in ['tulis', 'write', 'email', 'new', 'ke', 'to']:
    clean_args = re.sub(r'\b' + w + r'\b', '', clean_args, flags=re.IGNORECASE)
    
instruction = clean_args.strip()
print(f"DEBUG: Final Instruction: '{instruction}'")

if not instruction:
    print("❌ Mohon sertakan pesan/instruksi untuk emailnya.")
else:
    print(f"SUCCESS: From={from_account}, To={to_email}, Instruction={instruction}")
