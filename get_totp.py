import pyotp
import os
from dotenv import load_dotenv

def get_amazon_codes():
    load_dotenv()
    
    print("\n" + "="*40)
    print(" Amazon Seller Central 2FA Codes ")
    print("="*40)
    
    # Account 1
    secret1 = os.getenv("AMAZON_TOTP_SECRET")
    email1 = os.getenv("AMAZON_EMAIL", "Account 1")
    if secret1:
        totp = pyotp.TOTP(secret1)
        print(f"\n[{email1}]")
        print(f"Code:  {totp.now()}")
    else:
        print("\n[Account 1]")
        print("No secret found in .env (AMAZON_TOTP_SECRET)")

    # Account 2
    secret2 = os.getenv("AMAZON_TOTP_SECRET_2")
    email2 = os.getenv("AMAZON_EMAIL_2", "Account 2")
    if secret2 and secret2 != "YOUR_SECOND_SECRET_HERE":
        totp = pyotp.TOTP(secret2)
        print(f"\n[{email2}]")
        print(f"Code:  {totp.now()}")
    else:
        print("\n[Account 2]")
        print("Please add your second secret to .env (AMAZON_TOTP_SECRET_2)")

    # Helium 10
    helium_secret = os.getenv("HELIUM_TOTP_SECRET")
    if helium_secret and helium_secret != "YOUR_HELIUM_SECRET_HERE":
        totp = pyotp.TOTP(helium_secret)
        print(f"\n[Helium 10]")
        print(f"Code:  {totp.now()}")
        
    print("\n" + "="*40 + "\n")

if __name__ == "__main__":
    get_amazon_codes()
