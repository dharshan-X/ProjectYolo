from tools.artifact_ops import create_artifact, get_latest_artifact, list_artifacts
from tools.background_ops import dispatch_parallel_agents, run_background_mission
try:
    from tools.browser_ops import (
        browser_click,
        browser_click_at,
        browser_close,
        browser_crawl_step,
        browser_click_next,
        browser_extract_text,
        browser_navigate,
        browser_extract_links,
        browser_press_key,
        browser_screenshot,
        browser_scroll,
        browser_scroll_until_end,
        browser_type,
        browser_wait,
    )
    _BROWSER_AVAILABLE = True
except ImportError:
    _BROWSER_AVAILABLE = False
    browser_click = browser_click_at = browser_close = None
    browser_crawl_step = browser_click_next = browser_extract_text = None
    browser_navigate = browser_extract_links = browser_press_key = None
    browser_screenshot = browser_scroll = browser_scroll_until_end = None
    browser_type = browser_wait = None
from tools.cron_ops import (
    cancel_scheduled_task,
    get_scheduled_tasks,
    schedule_daily_task,
    schedule_task,
)
from tools.evolution_ops import (
    archive_proactive_memory,
    optimize_skill,
    self_upgrade_summary,
)
from tools.experience_ops import learn_experience, list_experiences
from tools.file_ops import (
    copy_file,
    delete_file,
    edit_file,
    file_info,
    list_dir,
    make_dir,
    move_file,
    read_file,
    search_in_file,
    send_to_telegram,
    write_file,
)
from tools.identity_ops import read_user_identity, update_user_identity
from tools.mcp_manager import list_mcp_servers
from tools.mcp_ops import mcp_list_tools, mcp_run_tool
from tools.memory_ops import memory_add, memory_delete, memory_list, memory_wipe, memory_search
from tools.media_ops import transcribe_audio
from tools.mission_ops import create_mission, read_mission, update_mission
from tools.research_ops import (
    research_clear,
    research_get_all_summaries,
    research_enqueue_from_crawl_step,
    research_get_next,
    research_queue_urls,
    research_store_summary,
)
from tools.skill_ops import develop_new_skill, list_skills, read_skill
from tools.system_ops import (
    run_bash,
    terminal_interactive_run,
    terminal_list,
    terminal_read,
    terminal_send,
    terminal_start,
    terminal_stop,
)
from tools.web_ops import browse_url, web_search
from tools.git_ops import (
    git_status,
    git_diff,
    git_log,
    git_commit,
    git_branch,
    git_stash,
)
try:
    from tools.gui_ops import (
        gui_mouse_move,
        gui_mouse_click,
        gui_type_text,
        gui_press_key,
        gui_screenshot,
        gui_send_screenshot,
        gui_get_screen_size,
        gui_analyze_screen,
        gui_find_element,
        gui_click_element,
        gui_observe_transition,
        gui_scroll_screen,
        gui_read_text_at,
    )
    _GUI_AVAILABLE = True
except Exception:
    _GUI_AVAILABLE = False
    gui_mouse_move = gui_mouse_click = gui_type_text = gui_press_key = None
    gui_screenshot = gui_send_screenshot = gui_get_screen_size = None
    gui_analyze_screen = gui_find_element = gui_click_element = None
    gui_observe_transition = gui_scroll_screen = gui_read_text_at = None
codebase_index = codebase_search = None
from tools.team_ops import (
    report_completion,
    request_help,
    spawn_worker,
    check_workers,
    spawn_team_discussion,
    cancel_all_workers,
    spawn_swarm,
    broadcast_swarm_message,
    read_swarm_messages,
    wait_for_swarm_message,
)
from tools.media_ops import generate_image
from tools.plugin_manager import PLUGIN_HANDLERS, PLUGIN_SCHEMAS

__all__ = [
    "TOOLS_SCHEMAS",
    "report_completion",
    "request_help",
    "spawn_worker",
    "check_workers",
    "spawn_team_discussion",
    "cancel_all_workers",
    "spawn_swarm",
    "broadcast_swarm_message",
    "read_swarm_messages",
    "wait_for_swarm_message",
    "copy_file",
    "delete_file",
    "edit_file",
    "file_info",
    "list_dir",
    "make_dir",
    "move_file",
    "read_file",
    "search_in_file",
    "write_file",
    "send_to_telegram",
    "list_skills",
    "read_skill",
    "develop_new_skill",
    "run_bash",
    "terminal_interactive_run",
    "terminal_list",
    "terminal_start",
    "terminal_send",
    "terminal_read",
    "terminal_stop",
    "create_mission",
    "read_mission",
    "update_mission",
    "create_artifact",
    "list_artifacts",
    "get_latest_artifact",
    "web_search",
    "browse_url",
    "browser_navigate",
    "browser_click",
    "browser_click_at",
    "browser_press_key",
    "browser_scroll",
    "browser_scroll_until_end",
    "browser_crawl_step",
    "browser_type",
    "browser_extract_links",
    "browser_click_next",
    "browser_screenshot",
    "browser_extract_text",
    "browser_wait",
    "browser_close",
    "research_queue_urls",
    "research_enqueue_from_crawl_step",
    "research_get_next",
    "research_store_summary",
    "research_get_all_summaries",
    "research_clear",
    "memory_list",
    "memory_search",
    "memory_wipe",
    "memory_add",
    "memory_delete",
    "mcp_list_tools",
    "mcp_run_tool",
    "list_mcp_servers",
    "learn_experience",
    "list_experiences",
    "run_background_mission",
    "dispatch_parallel_agents",
    "schedule_task",
    "schedule_daily_task",
    "get_scheduled_tasks",
    "cancel_scheduled_task",
    "optimize_skill",
    "archive_proactive_memory",
    "self_upgrade_summary",
    "read_user_identity",
    "update_user_identity",
    "gui_mouse_move",
    "gui_mouse_click",
    "gui_type_text",
    "gui_press_key",
    "gui_screenshot",
    "gui_send_screenshot",
    "gui_get_screen_size",
    "gui_analyze_screen",
    "gui_find_element",
    "gui_click_element",
    "gui_observe_transition",
    "gui_scroll_screen",
    "gui_read_text_at",
    "git_status",
    "git_diff",
    "git_log",
    "git_commit",
    "git_branch",
    "git_stash",
    "codebase_index",
    "codebase_search",
    "transcribe_audio",
    "generate_image",
]

# Define all schemas in one place for the agent
TOOLS_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "report_completion",
            "description": "Report that your assigned sub-task is successfully complete. This ends your execution loop.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "summary": {"type": "string", "description": "Summary of changes made"}
                },
                "required": ["task_id", "summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_help",
            "description": "Report that you are confused, stuck, or blocked. This pauses your execution so the Manager can intervene or spawn a team discussion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "reason": {"type": "string", "description": "Why you are stuck"},
                    "context": {"type": "string", "description": "Relevant file paths or errors"}
                },
                "required": ["task_id", "reason", "context"]
            }
        }
        },
        {
        "type": "function",
        "function": {
            "name": "spawn_worker",
            "description": "Spawn an isolated worker agent to handle a specific sub-task in the background. Useful for dividing and conquering.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "description": "The persona/role (e.g. 'Database Expert', 'Frontend Dev')"},
                    "objective": {"type": "string", "description": "Clear, detailed instructions for what the worker must accomplish."},
                    "model": {"type": "string", "description": "Optional model override (e.g. 'openai/gpt-4o' or 'claude-3-5-sonnet-20241022')"}
                },
                "required": ["role", "objective"]
            }
        }
        },
        {
        "type": "function",
        "function": {
            "name": "check_workers",
            "description": "Check the status of all spawned workers. Use this to see if they are 'completed', 'running', or 'needs_help'.",
            "parameters": {"type": "object", "properties": {}}
        }
        },
        {
        "type": "function",
        "function": {
            "name": "spawn_team_discussion",
            "description": "Start a peer-to-peer chat room discussion among virtual experts to solve a complex problem or unblock a worker. Returns the full transcript of the debate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The problem, context, and what needs to be decided."},
                    "roles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of personas to invite (e.g. ['Security Expert', 'Stuck Backend Worker', 'Database Architect'])"
                    },
                    "max_rounds": {"type": "integer", "description": "Max turns they take to debate (default 3, max 5)"},
                    "model": {"type": "string", "description": "Optional model override (e.g. 'openai/gpt-4o' or 'claude-3-5-sonnet-20241022')"}
                },
                "required": ["topic", "roles"]
            }
        }
        },
        {
        "type": "function",
        "function": {
            "name": "cancel_all_workers",
            "description": "Forcefully cancel all currently running background workers. Use this if the team is stuck or producing errors.",
            "parameters": {"type": "object", "properties": {}}
        }
        },
        {
        "type": "function",
        "function": {
            "name": "spawn_swarm",
            "description": "Manager tool: Create a new asynchronous Swarm to tackle a complex objective. Spawns a 'Swarm Lead' who manages sub-workers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "objective": {"type": "string", "description": "The overall mission for the swarm."},
                    "roles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of specialized roles needed (e.g. ['Researcher', 'Coder', 'Reviewer'])"
                    },
                    "model": {"type": "string", "description": "Optional model override (e.g. 'openai/gpt-4o' or 'claude-3-5-sonnet-20241022')"}
                },
                "required": ["objective", "roles"]
            }
        }
        },
        {
        "type": "function",
        "function": {
            "name": "broadcast_swarm_message",
            "description": "Worker tool: Broadcast a message to the shared swarm message bus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "swarm_id": {"type": "string"},
                    "task_id": {"type": "string"},
                    "role": {"type": "string"},
                    "message": {"type": "string"}
                },
                "required": ["swarm_id", "task_id", "role", "message"]
            }
        }
        },
        {
        "type": "function",
        "function": {
            "name": "read_swarm_messages",
            "description": "Worker tool: Read messages from the swarm's message bus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "swarm_id": {"type": "string"},
                    "limit": {"type": "integer"}
                },
                "required": ["swarm_id"]
            }
        }
        },
        {
        "type": "function",
        "function": {
            "name": "wait_for_swarm_message",
            "description": "Worker tool: Pause execution and wait until a message matching a regex pattern is broadcasted to the swarm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "swarm_id": {"type": "string"},
                    "pattern": {"type": "string", "description": "Regex pattern to match in the broadcasted messages."},
                    "timeout_seconds": {"type": "integer", "description": "Max seconds to wait. Defaults to 300."}
                },
                "required": ["swarm_id", "pattern"]
            }
        }
        },
        {
        "type": "function",
        "function": {
            "name": "update_user_identity",
            "description": "Refine the structural Markdown document that defines the user's engineering style, project preferences, and unstated goals. Use this to ensure I adapt to the user's specific way of working.",
            "parameters": {
                "type": "object",
                "properties": {
                    "observations": {
                        "type": "string",
                        "description": "The full updated Markdown content of the identity file.",
                    }
                },
                "required": ["observations"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_user_identity",
            "description": "Read the Master User Identity profile to understand how to best tailor my reasoning and code to the user's specific style.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_skill",
            "description": "Rewrite an existing skill manual with new improvements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "improvements": {"type": "string"},
                },
                "required": ["name", "improvements"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "archive_proactive_memory",
            "description": "Save a critical technical insight immediately.",
            "parameters": {
                "type": "object",
                "properties": {"insight": {"type": "string"}},
                "required": ["insight"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "self_upgrade_summary",
            "description": "Archive a structured summary of a self-upgrade (research, implementation, validation).",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_name": {"type": "string"},
                    "research_notes": {"type": "string"},
                    "implementation_notes": {"type": "string"},
                    "validation_notes": {"type": "string"},
                },
                "required": [
                    "feature_name",
                    "research_notes",
                    "implementation_notes",
                    "validation_notes",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_task",
            "description": "Schedule a recurring autonomous task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {"type": "string"},
                    "interval_minutes": {"type": "integer"},
                },
                "required": ["task_description", "interval_minutes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_daily_task",
            "description": "Schedule a recurring autonomous task that runs every day.",
            "parameters": {
                "type": "object",
                "properties": {"task_description": {"type": "string"}},
                "required": ["task_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_scheduled_tasks",
            "description": "List all active recurring tasks.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_scheduled_task",
            "description": "Stop and delete a recurring task by its ID.",
            "parameters": {
                "type": "object",
                "properties": {"cron_id": {"type": "integer"}},
                "required": ["cron_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dispatch_parallel_agents",
            "description": "Spawn multiple specialized agents in parallel as tracked background tasks. Optionally wait for completion to return combined results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "objectives": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "A list of specific instructions for each agent.",
                    },
                    "wait_for_completion": {
                        "type": "boolean",
                        "description": "If true, wait for all agents and return final outputs; otherwise return immediately with task IDs.",
                    },
                },
                "required": ["objectives"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_background_mission",
            "description": "Execute a highly complex task in the background.",
            "parameters": {
                "type": "object",
                "properties": {"objective": {"type": "string"}},
                "required": ["objective"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "learn_experience",
            "description": "Record a technical lesson or bug fix.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "error": {"type": "string"},
                    "resolution": {"type": "string"},
                },
                "required": ["task", "error", "resolution"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_experiences",
            "description": "List all technical lessons learned.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mcp_list_tools",
            "description": "List tools on an MCP server.",
            "parameters": {
                "type": "object",
                "properties": {"server_command": {"type": "string"}},
                "required": ["server_command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mcp_run_tool",
            "description": "Run an MCP tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_command": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "tool_args": {"type": "object"},
                },
                "required": ["server_command", "tool_name", "tool_args"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_mcp_servers",
            "description": "List configured MCP servers, their connection status, and loaded tool counts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "working_memory_set",
            "description": "Write a key-value scratchpad note for the current task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"}
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "working_memory_get",
            "description": "Read all working memory for the current task.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "working_memory_clear",
            "description": "Wipe scratchpad after task completes.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consolidate_memories",
            "description": "Manually trigger episodic to semantic memory promotion.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_stats",
            "description": "Show tier counts, categories, and last consolidation.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_add",
            "description": "Remember a user fact.",
            "parameters": {
                "type": "object",
                "properties": {"fact": {"type": "string"}},
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_delete",
            "description": "Delete a single specific memory by its unique ID (e.g., l3_1, l2_5).",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "The ID of the memory to delete.",
                    }
                },
                "required": ["memory_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_list",
            "description": "Get a high-level summary of stored memory counts and the 10 most recent facts. Does NOT return all memories.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Semantic search the permanent memory database for a specific keyword or question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query, e.g., 'What is my name?' or 'TypeScript'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_wipe",
            "description": "Delete user memories.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_queue_urls",
            "description": "Add URLs to persistent queue.",
            "parameters": {
                "type": "object",
                "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
                "required": ["urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_enqueue_from_crawl_step",
            "description": "Parse `browser_crawl_step` output, filter low-signal links, and enqueue high-quality URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "crawl_step_output": {"type": "string"},
                    "topic_hint": {"type": "string"},
                    "max_urls": {"type": "integer"},
                },
                "required": ["crawl_step_output"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_get_next",
            "description": "Get next URL from queue.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_store_summary",
            "description": "Store a site summary to disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["url", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_get_all_summaries",
            "description": "Retrieve all source summaries.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_clear",
            "description": "Delete research state.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate live browser.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click web element.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click_at",
            "description": "Click (x, y) coordinates.",
            "parameters": {
                "type": "object",
                "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press_key",
            "description": "Press a keyboard key.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Scroll page in multiple steps to load deeper content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["down", "up"]},
                    "pixels": {"type": "integer"},
                    "steps": {"type": "integer"},
                    "delay_seconds": {"type": "number"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll_until_end",
            "description": "Auto-scroll until page height stops growing on infinite-scroll pages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_rounds": {"type": "integer"},
                    "step_pixels": {"type": "integer"},
                    "settle_delay_seconds": {"type": "number"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_crawl_step",
            "description": "Run one crawl step: scroll to load content, extract links, optionally click next.",
            "parameters": {
                "type": "object",
                "properties": {
                    "link_limit": {"type": "integer"},
                    "same_domain": {"type": "boolean"},
                    "try_next": {"type": "boolean"},
                    "max_scroll_rounds": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_extract_links",
            "description": "Extract normalized links from current page for deep crawl/pagination.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "same_domain": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click_next",
            "description": "Click a next/load-more control to go beyond the first page.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "Type into input field.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "text": {"type": "string"},
                    "press_enter": {"type": "boolean"},
                },
                "required": ["selector", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Screenshot current page.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_extract_text",
            "description": "Extract visible text.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait",
            "description": "Pause browser execution.",
            "parameters": {
                "type": "object",
                "properties": {"seconds": {"type": "number"}},
                "required": ["seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "Close browser session.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the internet for real-time information. MANDATORY for all factual questions about the present-day world (roles, prices, laws, status). Follow COPYRIGHT rules: paraphrase results, max 15-word quotes, one quote per source.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse_url",
            "description": "Fetch and extract text content from a specific URL. Useful for deep research after a search. Follow COPYRIGHT rules: paraphrase results, max 15-word quotes, one quote per source.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "develop_new_skill",
            "description": "Record skill manual.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_to_telegram",
            "description": "Upload file to user.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_artifact",
            "description": "Generate persistent deliverable.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                    "file_type": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_artifacts",
            "description": "List artifacts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_latest_artifact",
            "description": "Upload the newest artifact file.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_mission",
            "description": "Initialize mission plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "objective": {"type": "string"},
                    "strategy": {"type": "string"},
                },
                "required": ["objective", "strategy"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_mission",
            "description": "Record mission progress.",
            "parameters": {
                "type": "object",
                "properties": {"step_description": {"type": "string"}},
                "required": ["step_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_mission",
            "description": "Read mission status.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "List available skills.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": "Read skill manual.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Execute a one-shot shell command and return stdout/stderr. Has a 5-minute timeout. Best for quick, non-interactive commands (ls, cat, grep, git status). For commands that may take longer than 5 minutes (npx, npm install, large git clone, docker build, compilation), or that prompt for input (y/n), use terminal_start + terminal_send + terminal_read instead.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_start",
            "description": "Start a persistent interactive PTY terminal session. Returns a session_id you must save. Use this when you need to: (1) interact with prompts (y/n, passwords, menus), (2) run long-lived processes (servers, watchers), (3) maintain shell state across commands (cd, exports, virtualenvs), (4) use tools like ssh, docker exec, python REPL, node REPL. Always call terminal_stop when done.",
            "parameters": {
                "type": "object",
                "properties": {
                    "shell": {
                        "type": "string",
                        "description": "Shell binary to use (default: $SHELL or /bin/bash). Examples: /bin/bash, /bin/zsh, python3, node.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory to start in.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_send",
            "description": "Send text input to an existing terminal session (like typing on a keyboard then pressing Enter). Use this to type commands, answer prompts (y/n), enter passwords, or send Ctrl sequences (use \\x03 for Ctrl-C, \\x04 for Ctrl-D). Set append_newline=false when sending raw keystrokes without Enter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "text": {"type": "string", "description": "Text to type. Use \\x03 for Ctrl-C, \\x04 for Ctrl-D, \\t for Tab."},
                    "append_newline": {"type": "boolean", "description": "If true (default), press Enter after typing. Set false for raw input like Ctrl-C."},
                    "read_after_send": {"type": "boolean", "description": "If true (default), read output after sending. Set false for fire-and-forget."},
                },
                "required": ["session_id", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_read",
            "description": "Read buffered output from a terminal session without sending any input. Use wait_seconds > 0 for slow commands (compilation, package install, test runs) to block until output appears instead of getting 'No new output'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "max_chars": {"type": "integer", "description": "Max characters to read (default: 30000)."},
                    "wait_seconds": {"type": "number", "description": "If > 0, poll until output appears or timeout. Useful for waiting on slow processes. Default 0 (instant read)."},
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_list",
            "description": "List all active terminal sessions with their session_id, status (running/exited), shell, working directory, age, and PID. Use this to find existing sessions to reuse instead of starting new ones, or to identify sessions that need cleanup.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_stop",
            "description": "Stop and clean up an interactive terminal session. Always call this when you are done with a session to avoid resource leaks. Use force=true for hung processes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "force": {"type": "boolean", "description": "If true, use SIGKILL instead of SIGTERM."},
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_interactive_run",
            "description": "Convenience: run a full interactive terminal flow in one call. Starts a session, sends a command, sends follow-up inputs (for prompts), reads all output, and optionally stops. Best for predictable multi-step interactions where you know all inputs upfront (e.g., npm init with known answers, apt install -y, configure scripts).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Initial command to run after session starts.",
                    },
                    "inputs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Follow-up input lines to send for interactive prompts.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory.",
                    },
                    "shell": {
                        "type": "string",
                        "description": "Shell binary (default: $SHELL).",
                    },
                    "stop_after": {
                        "type": "boolean",
                        "description": "If true (default), stop the session after collecting output.",
                    },
                    "force_stop": {
                        "type": "boolean",
                        "description": "If true and stopping, use SIGKILL.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace text in file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Copy a file or directory.",
            "parameters": {
                "type": "object",
                "properties": {"src": {"type": "string"}, "dest": {"type": "string"}},
                "required": ["src", "dest"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move or rename a file or directory.",
            "parameters": {
                "type": "object",
                "properties": {"src": {"type": "string"}, "dest": {"type": "string"}},
                "required": ["src", "dest"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List the contents of a directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_dir",
            "description": "Create a new directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_info",
            "description": "Get metadata.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compact_conversation",
            "description": "Summarize the current conversation history to save context space while preserving key technical details and mission progress.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_file",
            "description": "Search regex in file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "pattern": {"type": "string"},
                },
                "required": ["path", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_mouse_move",
            "description": "Move the mouse cursor to a specific (x, y) coordinate. Use carefully on GUI interfaces.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "duration": {
                        "type": "number",
                        "description": "Duration of the movement in seconds",
                    },
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_mouse_click",
            "description": "Click a mouse button.",
            "parameters": {
                "type": "object",
                "properties": {
                    "button": {"type": "string", "enum": ["left", "right", "middle"]},
                    "clicks": {"type": "integer", "description": "Number of clicks"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_type_text",
            "description": "Type a string of characters using the keyboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "interval": {
                        "type": "number",
                        "description": "Seconds between each key press",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_press_key",
            "description": "Press a single key or a hotkey combination (e.g., 'enter', 'ctrl+c').",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_screenshot",
            "description": "Take a screenshot and save it to the specified path.",
            "parameters": {
                "type": "object",
                "properties": {"save_path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_send_screenshot",
            "description": "Take a screenshot of the current screen and send it directly to the UI as an artifact.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_get_screen_size",
            "description": "Get the screen resolution.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_analyze_screen",
            "description": "[PERCEPTION — CALL THIS FIRST] Capture a screenshot, run OCR, detect all visible UI elements with bounding boxes, generate a Set-of-Mark annotated image. Returns structured JSON with screen_size, windows, elements (id, text, type, bbox, center), screenshot_path, and annotated_path. You MUST call this BEFORE any GUI interaction to understand what is on screen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "save_path": {
                        "type": "string",
                        "description": "Optional custom save path for screenshots",
                    },
                    "region": {
                        "type": "string",
                        "description": "Optional region to analyze as 'x,y,width,height'",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_find_element",
            "description": "[PERCEPTION] Find a GUI element by natural language description. Captures screenshot, runs OCR, fuzzy-matches description against detected text. Returns coordinates if found, or full list of visible elements if not — never guess.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Natural language description of the element to find, e.g. 'File menu', 'Save button', 'URL bar'",
                    }
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_click_element",
            "description": "[GROUNDED ACTION] Perception-based click: finds an element by description using OCR, then clicks its center. Use this instead of gui_mouse_move+gui_mouse_click to avoid coordinate hallucination. Returns what was clicked and exact coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "What to click, e.g. 'File menu', 'OK button'",
                    },
                    "button": {"type": "string", "enum": ["left", "right", "middle"]},
                    "clicks": {
                        "type": "integer",
                        "description": "Number of clicks (1=single, 2=double)",
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_observe_transition",
            "description": "[VERIFICATION] Compare before/after screen states to detect what changed. Call this after any GUI action to verify the result instead of assuming what happened.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_description": {
                        "type": "string",
                        "description": "What action was just performed",
                    },
                    "wait_seconds": {
                        "type": "number",
                        "description": "Seconds to wait before capturing 'after' state (default 1.0)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_scroll_screen",
            "description": "[GROUNDED ACTION] Scroll and return what is now visible via OCR. Unlike blind scrolling, this tells you exactly what appeared on screen after scrolling.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "amount": {
                        "type": "integer",
                        "description": "Scroll amount in notches (default 3)",
                    },
                    "region": {
                        "type": "string",
                        "description": "Optional region to analyze as 'x,y,width,height'",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gui_read_text_at",
            "description": "[PERCEPTION] OCR a specific screen region to read the exact text there. Use when you need to read text at known coordinates instead of guessing content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": "Left coordinate of region",
                    },
                    "y": {"type": "integer", "description": "Top coordinate of region"},
                    "width": {"type": "integer", "description": "Width of region"},
                    "height": {"type": "integer", "description": "Height of region"},
                },
                "required": ["x", "y", "width", "height"],
            },
        },
    },
    # ── Git Operations ──
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Get the current git repository status: branch name, staged/modified/untracked files, and ahead/behind counts. Returns structured JSON.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show the diff for modified files. Use `staged=true` to see staged changes. Optionally specify a path to diff a single file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Optional file path to diff",
                    },
                    "staged": {
                        "type": "boolean",
                        "description": "If true, show staged (cached) changes instead of working tree",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Show recent commit history. Returns up to `count` commits (max 50).",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of commits to show (default 10, max 50)",
                    },
                    "oneline": {
                        "type": "boolean",
                        "description": "If true (default), use compact one-line format",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Create a git commit with the given message. Use `add_all=true` to stage all changes before committing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message"},
                    "add_all": {
                        "type": "boolean",
                        "description": "If true, run `git add -A` before committing",
                    },
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_branch",
            "description": "List, create, switch, or delete branches. Call with no name to list all branches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Branch name (omit to list all)",
                    },
                    "switch": {
                        "type": "boolean",
                        "description": "If true, switch to the named branch",
                    },
                    "delete": {
                        "type": "boolean",
                        "description": "If true, delete the named branch",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_stash",
            "description": "Manage the git stash. Actions: list, push, pop, apply.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "push", "pop", "apply"],
                        "description": "Stash action (default: list)",
                    },
                    "message": {
                        "type": "string",
                        "description": "Optional message when pushing a stash",
                    },
                },
            },
        },
    },
    # ── Codebase RAG Operations ──
    {
        "type": "function",
        "function": {
            "name": "codebase_index",
            "description": "Recursively scans the workspace, generates embeddings for all code files, and indexes them in a local vector database for semantic search. Do this when the codebase changes significantly or before searching for the first time.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "codebase_search",
            "description": "Search the entire codebase using semantic similarity. Returns the top matching code chunks. Very useful for 'Where is X used?' or 'How does Y work?' questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The semantic query, e.g. 'How is the LLM router initialized?'",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transcribe_audio",
            "description": "Transcribe an audio file (mp3, webm, wav, m4a, etc.) into text using the AI pipeline. Supports filenames from the uploads directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the audio file or just the filename if stored in artifacts/uploads."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Generate an image from a text prompt, save it to artifacts, and send it back to the UI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Detailed image generation prompt."
                    }
                },
                "required": ["prompt"]
            }
        }
    }
]

# Append any dynamically loaded plugin schemas
if PLUGIN_SCHEMAS:
    TOOLS_SCHEMAS.extend(PLUGIN_SCHEMAS)

# Strip browser tool schemas if camoufox is not installed
if not _BROWSER_AVAILABLE:
    _BROWSER_TOOL_NAMES = {
        "browser_navigate", "browser_click", "browser_click_at", "browser_close",
        "browser_crawl_step", "browser_click_next", "browser_extract_text",
        "browser_extract_links", "browser_press_key", "browser_screenshot",
        "browser_scroll", "browser_scroll_until_end", "browser_type", "browser_wait",
    }
    TOOLS_SCHEMAS = [s for s in TOOLS_SCHEMAS if s.get("function", {}).get("name") not in _BROWSER_TOOL_NAMES]
else:
    _BROWSER_TOOL_NAMES = set()

if not _GUI_AVAILABLE:
    _GUI_TOOL_NAMES = {
        "gui_mouse_move", "gui_mouse_click", "gui_type_text", "gui_press_key",
        "gui_screenshot", "gui_send_screenshot", "gui_get_screen_size",
        "gui_analyze_screen", "gui_find_element", "gui_click_element",
        "gui_observe_transition", "gui_scroll_screen", "gui_read_text_at",
    }
    TOOLS_SCHEMAS = [
        s for s in TOOLS_SCHEMAS
        if s.get("function", {}).get("name") not in _GUI_TOOL_NAMES
    ]
else:
    _GUI_TOOL_NAMES = set()


def validate_tool_schema_alignment() -> dict:
    """Return schema/handler drift so startup checks and tests can catch it."""
    from tools.registry import TOOL_REGISTRY

    lazy_tool_names = {"codebase_index", "codebase_search"}
    schema_names = {
        schema.get("function", {}).get("name")
        for schema in TOOLS_SCHEMAS
        if schema.get("function", {}).get("name")
    }
    handler_names = (
        set(TOOL_REGISTRY)
        | set(PLUGIN_HANDLERS)
        | {"compact_conversation"}
        | lazy_tool_names
    )
    handler_names -= _BROWSER_TOOL_NAMES | _GUI_TOOL_NAMES
    return {
        "schemas_without_handlers": sorted(schema_names - handler_names),
        "handlers_without_schemas": sorted(handler_names - schema_names),
    }


_TOOL_SCHEMA_DRIFT = validate_tool_schema_alignment()
if _TOOL_SCHEMA_DRIFT["schemas_without_handlers"] or _TOOL_SCHEMA_DRIFT["handlers_without_schemas"]:
    from tools.base import audit_log

    audit_log("tool_schema_alignment", _TOOL_SCHEMA_DRIFT, "error", "Tool schema drift detected")
