
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eleuthia.tools.connector_email import EmailHandler
handler = EmailHandler()
print("Loaded Accounts:")
for acc in handler.get_all_accounts():
    print(f"- Name: {acc['name']}, User: {acc.get('username', 'N/A')}")
