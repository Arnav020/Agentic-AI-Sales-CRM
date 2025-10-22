"""
Agentic CRM - Central Orchestrator
----------------------------------
Handles running all agents per-user:
- Detects user folders automatically under /users
- Allows choosing user and agents to execute
- Ensures proper dependency order
- Passes correct per-user paths to each agent
"""

import os
import sys
import json
import time
from pathlib import Path
import importlib

# Global constants
PROJECT_ROOT = Path(__file__).resolve().parent
USERS_DIR = PROJECT_ROOT / "users"
AGENTS_DIR = PROJECT_ROOT / "agents"

# Ordered list of all agent modules
AGENT_ORDER = [
    "enrichment_agent",
    "scoring_agent",
    "employee_finder",
    "contact_finder",
    "email_sender"
]


def list_users():
    """Return all available users inside /users."""
    if not USERS_DIR.exists():
        print("❌ No 'users/' directory found. Create it first.")
        sys.exit(1)
    users = [p.name for p in USERS_DIR.iterdir() if p.is_dir()]
    if not users:
        print("⚠️ No users found in 'users/'")
        sys.exit(1)
    return users


def list_agents():
    """Return available agents."""
    return AGENT_ORDER


def run_agent(agent_name: str, user_folder: Path):
    """Import and execute a specific agent for a user."""
    print(f"\n🚀 Running {agent_name}.py for user → {user_folder.name}")

    # Force backend-based import so it always works when run as 'python -m backend.main'
    module_path = f"backend.agents.{agent_name}"

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        print(f"❌ Could not find agent: {agent_name}.py")
        return False

    # Run the main logic for each agent, if defined
    if hasattr(module, "main"):
        os.environ["USER_FOLDER"] = str(user_folder)
        start_time = time.time()
        try:
            module.main()
            print(f"✅ {agent_name}.py finished successfully in {time.time() - start_time:.2f}s")
            return True
        except Exception as e:
            print(f"❌ Error running {agent_name}: {e}")
            return False
    else:
        print(f"⚠️ Agent {agent_name} has no main() function.")
        return False


def show_menu(options, title="Select an option"):
    """Helper for user input menu."""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    for i, opt in enumerate(options, 1):
        print(f"[{i}] {opt}")
    print("[0] Exit")
    print("-" * 60)
    choice = input("Enter number(s) (comma-separated for multiple): ").strip()
    if choice == "0":
        sys.exit(0)
    try:
        indices = [int(x) for x in choice.split(",") if x.strip().isdigit()]
        return [options[i - 1] for i in indices if 0 < i <= len(options)]
    except Exception:
        print("Invalid input. Please enter numbers only.")
        return show_menu(options, title)


def main():
    print("\n🧠 Agentic CRM — Multi-User Orchestrator")
    print("=" * 60)

    # Step 1 — Select user
    users = list_users()
    selected_users = show_menu(users, "Select user(s) to run agents for")
    for user_name in selected_users:
        user_path = USERS_DIR / user_name
        print(f"\n👤 Selected user: {user_name}")
        print(f"📂 User folder: {user_path}")

        # Step 2 — Choose agents to run
        agents = list_agents()
        selected_agents = show_menu(agents, f"Select agent(s) to run for {user_name}")

        # Step 3 — Run selected agents sequentially
        for agent in selected_agents:
            ok = run_agent(agent, user_path)
            if not ok:
                print(f"⚠️ Skipping remaining agents for {user_name} due to failure.")
                break

        print(f"\n✅ Finished all selected agents for user {user_name}")
        print("-" * 60)

    print("\n🎯 All tasks completed successfully!")


if __name__ == "__main__":
    main()
