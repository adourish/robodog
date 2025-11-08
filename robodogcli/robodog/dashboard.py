# file: dashboard.py
#!/usr/bin/env python3
"""Interactive dashboard and status display for Robodog."""

import os
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class Dashboard:
    """Display real-time status and statistics for Robodog tasks."""
    
    def __init__(self, todo_service):
        self.todo_service = todo_service
        
    def clear_screen(self):
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def get_status_emoji(self, task: Dict[str, Any]) -> str:
        """Get emoji representation of task status."""
        plan = task.get('plan', ' ')
        llm = task.get('llm', ' ')
        commit = task.get('commit', ' ')
        
        if plan == 'x' and llm == 'x' and commit == 'x':
            return '✅ Complete'
        elif plan == '~' or llm == '~' or commit == '~':
            return '⚙️ In Progress'
        elif plan == 'x' and llm == 'x' and commit == ' ':
            return '📦 Ready to Commit'
        elif plan == 'x' and llm == ' ':
            return '💻 Ready for Code'
        elif plan == ' ':
            return '📝 Ready for Plan'
        else:
            return '⏸️ Paused'
    
    def get_statistics(self) -> Dict[str, Any]:
        """Calculate task statistics."""
        tasks = self.todo_service._tasks
        
        total = len(tasks)
        completed = sum(1 for t in tasks if t.get('plan') == 'x' and t.get('llm') == 'x' and t.get('commit') == 'x')
        in_progress = sum(1 for t in tasks if t.get('plan') == '~' or t.get('llm') == '~' or t.get('commit') == '~')
        pending = total - completed - in_progress
        
        # Token statistics
        total_tokens = sum(
            t.get('knowledge_tokens', 0) + 
            t.get('include_tokens', 0) + 
            t.get('prompt_tokens', 0) + 
            t.get('plan_tokens', 0)
            for t in tasks
        )
        
        # Estimate cost (rough estimate: $0.01 per 1000 tokens)
        estimated_cost = (total_tokens / 1000) * 0.01
        
        return {
            'total': total,
            'completed': completed,
            'in_progress': in_progress,
            'pending': pending,
            'total_tokens': total_tokens,
            'estimated_cost': estimated_cost
        }
    
    def show_full_dashboard(self):
        """Display comprehensive status dashboard."""
        self.clear_screen()
        
        print("╔═══════════════════════════════════════════════════════╗")
        print("║              🤖 ROBODOG DASHBOARD                     ║")
        print("╚═══════════════════════════════════════════════════════╝")
        
        # Current task
        tasks = self.todo_service._tasks
        in_progress = [t for t in tasks if t.get('plan') == '~' or t.get('llm') == '~' or t.get('commit') == '~']
        
        if in_progress:
            current = in_progress[0]
            print(f"\n📌 Current Task: {current['desc'][:50]}")
            print(f"   Status: {self.get_status_emoji(current)}")
            print(f"   File: {current.get('file', 'N/A')}")
            
            # Show progress bars
            plan_status = '✅' if current.get('plan') == 'x' else '⚙️' if current.get('plan') == '~' else '⏳'
            llm_status = '✅' if current.get('llm') == 'x' else '⚙️' if current.get('llm') == '~' else '⏳'
            commit_status = '✅' if current.get('commit') == 'x' else '⚙️' if current.get('commit') == '~' else '⏳'
            
            print(f"\n   📝 Plan   : {'██████████' if current.get('plan') == 'x' else '█████░░░░░' if current.get('plan') == '~' else '──────────'} {plan_status}")
            print(f"   💻 Code   : {'██████████' if current.get('llm') == 'x' else '█████░░░░░' if current.get('llm') == '~' else '──────────'} {llm_status}")
            print(f"   📦 Commit : {'██████████' if current.get('commit') == 'x' else '█████░░░░░' if current.get('commit') == '~' else '──────────'} {commit_status}")
        else:
            print("\n📌 No task currently in progress")
        
        # Statistics
        stats = self.get_statistics()
        print(f"\n📊 Statistics:")
        print(f"   Total tasks: {stats['total']}")
        print(f"   Completed: {stats['completed']} ✅")
        print(f"   In progress: {stats['in_progress']} ⚙️")
        print(f"   Pending: {stats['pending']} ⏳")
        
        # Token usage
        print(f"\n💰 Token Usage:")
        print(f"   Total: {stats['total_tokens']:,} tokens")
        print(f"   Estimated cost: ${stats['estimated_cost']:.2f}")
        
        # Pending tasks
        pending = [t for t in tasks if t.get('plan') == ' ' or (t.get('plan') == 'x' and t.get('llm') == ' ') or (t.get('llm') == 'x' and t.get('commit') == ' ')]
        if pending:
            print(f"\n📋 Next Tasks:")
            for i, task in enumerate(pending[:3], 1):
                step = 'Plan' if task.get('plan') == ' ' else 'Code' if task.get('llm') == ' ' else 'Commit'
                print(f"   {i}. [{step}] {task['desc'][:45]}")
            if len(pending) > 3:
                print(f"   ... and {len(pending) - 3} more")
        
        print("\n" + "─" * 57)
        print("Commands: /status | /todo | /pause | /resume | /help")
        print("─" * 57)
    
    def show_quick_status(self):
        """Display quick one-line status."""
        stats = self.get_statistics()
        in_progress = [t for t in self.todo_service._tasks if t.get('plan') == '~' or t.get('llm') == '~' or t.get('commit') == '~']
        
        if in_progress:
            current = in_progress[0]
            step = 'Plan' if current.get('plan') == '~' else 'Code' if current.get('llm') == '~' else 'Commit'
            print(f"⚙️ [{step}] {current['desc'][:40]} | {stats['completed']}/{stats['total']} done | {stats['total_tokens']:,} tokens")
        else:
            print(f"✅ {stats['completed']}/{stats['total']} tasks complete | {stats['pending']} pending | {stats['total_tokens']:,} tokens")


class TaskSelector:
    """Interactive task selection menu."""
    
    def __init__(self, todo_service):
        self.todo_service = todo_service
    
    def show_menu(self) -> Optional[Dict[str, Any]]:
        """Display interactive task menu and return selected task."""
        tasks = self.todo_service._tasks
        pending = [
            t for t in tasks 
            if t.get('plan') == ' ' or t.get('llm') == ' ' or t.get('commit') == ' '
        ]
        
        if not pending:
            print("✅ No pending tasks")
            return None
        
        print("\n╔═══════════════════════════════════════════════════════╗")
        print("║              📋 SELECT TASK                           ║")
        print("╚═══════════════════════════════════════════════════════╝\n")
        
        for i, task in enumerate(pending, 1):
            step = 'Plan' if task.get('plan') == ' ' else 'Code' if task.get('llm') == ' ' else 'Commit'
            desc = task['desc'][:50]
            tokens = task.get('include_tokens', 0) + task.get('knowledge_tokens', 0)
            print(f"  {i}. [{step:6}] {desc:<50} ({tokens:,} tokens)")
        
        print(f"\n  0. Run next task automatically")
        print(f"  q. Cancel")
        
        try:
            choice = input(f"\nSelect task (1-{len(pending)}, 0, q): ").strip().lower()
            if choice == 'q':
                return None
            if choice == '0':
                return pending[0]
            idx = int(choice) - 1
            if 0 <= idx < len(pending):
                return pending[idx]
            print("❌ Invalid selection")
            return None
        except (ValueError, KeyboardInterrupt):
            return None


class CommitConfirmation:
    """Confirmation dialog for commit operations."""
    
    @staticmethod
    def confirm(task: Dict[str, Any], files: List[str]) -> bool:
        """Ask user to confirm before committing changes."""
        print("\n╔═══════════════════════════════════════════════════════╗")
        print("║              ⚠️  COMMIT CONFIRMATION                  ║")
        print("╚═══════════════════════════════════════════════════════╝")
        
        print(f"\nTask: {task['desc']}")
        print(f"\n📁 Files to be modified ({len(files)}):")
        for f in files[:10]:  # Show first 10
            print(f"   • {f}")
        if len(files) > 10:
            print(f"   ... and {len(files) - 10} more files")
        
        print("\nOptions:")
        print("  y - Yes, commit changes")
        print("  n - No, cancel")
        print("  p - Preview changes")
        
        try:
            response = input("\nProceed? (y/n/p): ").strip().lower()
            if response == 'p':
                print("\n📄 Preview not yet implemented")
                return CommitConfirmation.confirm(task, files)
            return response == 'y'
        except KeyboardInterrupt:
            return False


class TokenBudgetDisplay:
    """Display token usage and budget."""
    
    @staticmethod
    def show(used: int, max_budget: int = 100000):
        """Display token usage progress bar."""
        percent = min((used / max_budget) * 100, 100)
        bar_length = 40
        filled = int(bar_length * percent / 100)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        # Color coding
        if percent < 70:
            status = '🟢 Good'
        elif percent < 90:
            status = '🟡 Warning'
        else:
            status = '🔴 High'
        
        print(f"\n💰 Token Budget: [{bar}] {used:,}/{max_budget:,} ({percent:.1f}%) {status}")
        
        if percent > 90:
            print("   ⚠️  Approaching token limit!")


def show_shortcuts():
    """Display available keyboard shortcuts."""
    print("\n⌨️  Available Commands:")
    print("  /status      - Show full dashboard")
    print("  /q           - Quick status")
    print("  /todo        - Select and run task")
    print("  /pause       - Pause agent loop")
    print("  /resume      - Resume agent loop")
    print("  /budget      - Show token budget")
    print("  /help        - Show all commands")
    print("  /clear       - Clear screen")
    print("  Ctrl+C       - Cancel operation")
