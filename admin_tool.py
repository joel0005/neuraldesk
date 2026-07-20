"""Admin Tool — manage clients remotely. Run: python admin_tool.py"""

import requests
import sys

# Change these for remote access
SERVER = "http://localhost:5000"
ADMIN_KEY = "neuraldesk-admin-2026"

headers = {"X-Admin-Key": ADMIN_KEY}


def show_menu():
    print("\n=== NeuralDesk Admin Panel ===")
    print("1. View all users")
    print("2. View user's bots")
    print("3. Change user plan")
    print("4. Platform stats")
    print("5. Delete user")
    print("6. Exit")
    return input("\nChoice: ").strip()


def list_users():
    r = requests.get(f"{SERVER}/api/admin/users", headers=headers)
    users = r.json()
    print(f"\n{'Email':<30} {'Name':<15} {'Plan':<15} {'ID'}")
    print("-" * 80)
    for u in users:
        print(f"{u['email']:<30} {u.get('name',''):<15} {u.get('plan','free'):<15} {u['id'][:8]}...")


def view_bots():
    user_id = input("User ID (or email): ").strip()

    # If email, find user ID
    if "@" in user_id:
        r = requests.get(f"{SERVER}/api/admin/users", headers=headers)
        users = r.json()
        found = [u for u in users if u["email"] == user_id]
        if not found:
            print("User not found")
            return
        user_id = found[0]["id"]

    r = requests.get(f"{SERVER}/api/admin/users/{user_id}/bots", headers=headers)
    bots = r.json()
    print(f"\n{'Name':<25} {'Provider':<10} {'Model':<20} {'Status'}")
    print("-" * 70)
    for b in bots:
        print(f"{b['name']:<25} {b.get('llm_provider',''):<10} {b.get('llm_model',''):<20} {b.get('status','')}")


def change_plan():
    user_id = input("User ID (or email): ").strip()

    if "@" in user_id:
        r = requests.get(f"{SERVER}/api/admin/users", headers=headers)
        users = r.json()
        found = [u for u in users if u["email"] == user_id]
        if not found:
            print("User not found")
            return
        user_id = found[0]["id"]

    print("\nAvailable plans:")
    print("  free            — 1 bot")
    print("  pro             — 5 bots")
    print("  business        — unlimited")
    print("  onpremise       — 1 bot (one-time payment)")
    print("  onpremise_5     — 5 bots (one-time payment)")
    print("  onpremise_unlimited — unlimited (one-time payment)")

    plan = input("\nNew plan: ").strip()
    r = requests.put(f"{SERVER}/api/admin/users/{user_id}/plan", headers=headers, json={"plan": plan})
    print(r.json())


def platform_stats():
    r = requests.get(f"{SERVER}/api/admin/stats", headers=headers)
    data = r.json()
    print(f"\n  Users: {data['total_users']}")
    print(f"  Bots: {data['total_bots']}")
    print(f"  Messages: {data['total_messages']}")
    print(f"  Sources: {data['total_sources']}")


def delete_user():
    user_id = input("User ID (or email): ").strip()

    if "@" in user_id:
        r = requests.get(f"{SERVER}/api/admin/users", headers=headers)
        users = r.json()
        found = [u for u in users if u["email"] == user_id]
        if not found:
            print("User not found")
            return
        user_id = found[0]["id"]

    confirm = input("Are you sure? Type 'yes': ").strip()
    if confirm == "yes":
        r = requests.delete(f"{SERVER}/api/admin/users/{user_id}", headers=headers)
        print(r.json())


# Main
while True:
    choice = show_menu()
    if choice == "1": list_users()
    elif choice == "2": view_bots()
    elif choice == "3": change_plan()
    elif choice == "4": platform_stats()
    elif choice == "5": delete_user()
    elif choice == "6": break
    else: print("Invalid choice")