"""
Generate realistic credit union mock data and write to data/raw/*.csv.
Run from the project root: python data/generate_mock_data.py
"""
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SEED = 42
random.seed(SEED)

N_MEMBERS = 500
N_ACCOUNTS = 800
N_LOANS = 350

RAW_DIR = Path(__file__).parent / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Name / location pools
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Barbara", "David", "Elizabeth", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Dorothy", "Paul", "Kimberly", "Andrew", "Emily", "Kenneth", "Donna",
    "George", "Michelle", "Joshua", "Carol", "Kevin", "Amanda", "Brian", "Melissa",
    "Edward", "Deborah", "Ronald", "Stephanie", "Timothy", "Rebecca", "Jason", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy",
    "Nicholas", "Angela", "Eric", "Shirley", "Jonathan", "Anna", "Stephen", "Brenda",
    "Larry", "Pamela", "Justin", "Emma", "Scott", "Nicole", "Brandon", "Helen",
    "Raymond", "Samantha", "Frank", "Katherine", "Gregory", "Christine", "Benjamin", "Debra",
    "Samuel", "Rachel", "Patrick", "Carolyn", "Alexander", "Janet", "Jack", "Catherine",
    "Dennis", "Maria", "Jerry", "Heather",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker",
    "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales", "Murphy",
    "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson", "Bailey",
    "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson",
    "Watson", "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray", "Mendoza",
    "Ruiz", "Hughes", "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers",
    "Long", "Ross", "Foster", "Jimenez",
]

ZIP_CODES = [
    "10001", "10002", "10003", "10010", "10016", "10019", "10022", "10036",
    "90001", "90002", "90011", "90021", "90031", "90041", "90051", "90061",
    "60601", "60602", "60603", "60604", "60605", "60606", "60607", "60608",
    "77001", "77002", "77003", "77004", "77005", "77006", "77007", "77008",
    "85001", "85002", "85003", "85004", "85005", "85006", "85007", "85008",
    "30301", "30302", "30303", "30304", "30305", "30306", "30307", "30308",
    "98101", "98102", "98103", "98104", "98105", "98106", "98107", "98108",
    "19101", "19102", "19103", "19104", "19105", "19106", "19107", "19108",
]

SEGMENTS = ["premium", "standard", "basic"]
SEGMENT_WEIGHTS = [0.20, 0.55, 0.25]

ACCOUNT_TYPES = ["checking", "savings", "money_market", "cd"]
LOAN_TYPES = ["auto", "mortgage", "personal", "heloc"]

ACCOUNT_STATUS = ["active", "active", "active", "active", "closed", "frozen"]
LOAN_STATUS = ["current", "current", "current", "current", "delinquent", "paid_off", "charged_off"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def rand_balance(lo: float, hi: float) -> float:
    return round(random.uniform(lo, hi), 2)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------
def generate_members(n: int) -> pd.DataFrame:
    today = date.today()
    rows = []
    used_emails: set[str] = set()

    for i in range(1, n + 1):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)

        base_email = f"{first.lower()}.{last.lower()}"
        email = f"{base_email}@example.com"
        # deduplicate
        suffix = 1
        while email in used_emails:
            email = f"{base_email}{suffix}@example.com"
            suffix += 1
        used_emails.add(email)

        dob = rand_date(date(1945, 1, 1), date(2000, 12, 31))
        member_since = rand_date(date(1995, 1, 1), today)

        # ~5% null segment, ~3% null zip to test cleaning
        segment = random.choices(SEGMENTS, SEGMENT_WEIGHTS)[0] if random.random() > 0.05 else None
        zip_code = random.choice(ZIP_CODES) if random.random() > 0.03 else None

        rows.append({
            "member_number": f"MBR{i:05d}",
            "first_name": first,
            "last_name": last,
            "email": email,
            "date_of_birth": dob.isoformat(),
            "member_since": member_since.isoformat(),
            "segment": segment,
            "zip_code": zip_code,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
def generate_accounts(members_df: pd.DataFrame, n: int) -> pd.DataFrame:
    today = date.today()
    member_ids = members_df["member_number"].tolist()

    # 60 % of members get a checking account (guaranteed first pass)
    checking_members = random.sample(member_ids, k=int(len(member_ids) * 0.60))

    rows = []
    for mbr in checking_members:
        member_since = date.fromisoformat(
            members_df.loc[members_df["member_number"] == mbr, "member_since"].iloc[0]
        )
        opened = rand_date(member_since, today)
        rows.append({
            "member_number": mbr,
            "account_type": "checking",
            "balance": rand_balance(100, 25_000),
            "opened_date": opened.isoformat(),
            "status": random.choice(ACCOUNT_STATUS),
        })

    # Fill remaining accounts with weighted random types
    remaining = n - len(rows)
    type_weights = [0.15, 0.45, 0.25, 0.15]  # checking/savings/mm/cd for extras
    for _ in range(remaining):
        mbr = random.choice(member_ids)
        member_since = date.fromisoformat(
            members_df.loc[members_df["member_number"] == mbr, "member_since"].iloc[0]
        )
        opened = rand_date(member_since, today)
        acct_type = random.choices(ACCOUNT_TYPES, type_weights)[0]

        balance_ranges = {
            "checking": (0, 30_000),
            "savings": (500, 75_000),
            "money_market": (2_500, 150_000),
            "cd": (1_000, 100_000),
        }
        lo, hi = balance_ranges[acct_type]

        rows.append({
            "member_number": mbr,
            "account_type": acct_type,
            "balance": rand_balance(lo, hi),
            "opened_date": opened.isoformat(),
            "status": random.choice(ACCOUNT_STATUS),
        })

    df = pd.DataFrame(rows)
    df.insert(0, "id", range(1, len(df) + 1))
    return df.sample(frac=1, random_state=SEED).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Loans
# ---------------------------------------------------------------------------
def generate_loans(members_df: pd.DataFrame, n: int) -> pd.DataFrame:
    today = date.today()
    member_ids = members_df["member_number"].tolist()

    # 40 % of members have at least one loan
    loan_members = random.sample(member_ids, k=int(len(member_ids) * 0.40))

    # Assign base loan; distribute remainder randomly among same pool
    assigned = list(loan_members)
    while len(assigned) < n:
        assigned.append(random.choice(loan_members))
    assigned = assigned[:n]

    loan_params = {
        "auto":      {"orig": (5_000,   60_000),  "term_years": (3,  7),  "rate": (0.0399, 0.0899)},
        "mortgage":  {"orig": (80_000, 600_000),  "term_years": (15, 30), "rate": (0.0299, 0.0699)},
        "personal":  {"orig": (1_000,   35_000),  "term_years": (1,  5),  "rate": (0.0699, 0.1799)},
        "heloc":     {"orig": (10_000, 250_000),  "term_years": (10, 20), "rate": (0.0549, 0.0999)},
    }
    type_weights = [0.30, 0.35, 0.25, 0.10]

    rows = []
    for mbr in assigned:
        member_since = date.fromisoformat(
            members_df.loc[members_df["member_number"] == mbr, "member_since"].iloc[0]
        )
        loan_type = random.choices(LOAN_TYPES, type_weights)[0]
        p = loan_params[loan_type]

        orig_bal = rand_balance(*p["orig"])
        term_years = random.randint(*p["term_years"])
        rate = round(random.uniform(*p["rate"]), 4)

        orig_date = rand_date(member_since, today)
        mat_date = date(
            orig_date.year + term_years,
            orig_date.month,
            orig_date.day,
        )

        # Current balance: random paydown between 0–100 %
        pct_paid = random.uniform(0.0, 1.0)
        curr_bal = round(orig_bal * (1 - pct_paid), 2)

        # Derive status from paydown
        if pct_paid >= 0.999:
            status = "paid_off"
        elif mat_date < today and pct_paid < 0.999:
            status = "charged_off"
        else:
            status = random.choices(
                ["current", "delinquent"],
                weights=[0.92, 0.08]
            )[0]

        rows.append({
            "member_number": mbr,
            "loan_type": loan_type,
            "original_balance": orig_bal,
            "current_balance": curr_bal,
            "interest_rate": rate,
            "origination_date": orig_date.isoformat(),
            "maturity_date": mat_date.isoformat(),
            "status": status,
        })

    df = pd.DataFrame(rows)
    df.insert(0, "id", range(1, len(df) + 1))
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Generating members...")
    members = generate_members(N_MEMBERS)
    members.to_csv(RAW_DIR / "members.csv", index=False)
    print(f"  {len(members)} members → data/raw/members.csv")

    print("Generating accounts...")
    accounts = generate_accounts(members, N_ACCOUNTS)
    accounts.to_csv(RAW_DIR / "accounts.csv", index=False)
    print(f"  {len(accounts)} accounts → data/raw/accounts.csv")

    print("Generating loans...")
    loans = generate_loans(members, N_LOANS)
    loans.to_csv(RAW_DIR / "loans.csv", index=False)
    print(f"  {len(loans)} loans → data/raw/loans.csv")

    # Quick sanity print
    print("\nSample member:")
    print(members.head(3).to_string(index=False))
    print("\nAccount type distribution:")
    print(accounts["account_type"].value_counts().to_string())
    print("\nLoan type distribution:")
    print(loans["loan_type"].value_counts().to_string())
