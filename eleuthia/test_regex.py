import re

text = "/tulis_email ke fajar.arif@haldin-natural.com tolong kirim laporan"
# Mimic _quick_intent_check
cmd = text[1:].split()[0]
raw_args = text[1:].replace(cmd, '', 1).strip()
print(f"Raw Args: '{raw_args}'")

# Current Regex
regex = r'[\w\.-]+@[\w\.-]+\.\w+'
match = re.search(regex, raw_args)
print(f"Match: {match.group(0) if match else 'None'}")

# Test with hyphen validity
test_str = "fajar.arif@haldin-natural.com"
match2 = re.search(regex, test_str)
print(f"Match2: {match2.group(0) if match2 else 'None'}")
