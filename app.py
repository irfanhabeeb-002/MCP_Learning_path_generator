import streamlit as st

from utils import AgentTimeoutError, ConfigurationError, run_agent_sync

st.set_page_config(
    page_title="AI Learning Path Generator | Personalized Roadmaps with MCP",
    page_icon="🚀",
    layout="wide"
)

st.title("AI Learning Path Generator")
st.caption(
    "Generate personalized learning roadmaps using LangGraph agents, Gemini 2.5 Flash, and MCP-powered resource discovery."
)

# Initialize session state for progress
if "current_step" not in st.session_state:
    st.session_state.current_step = ""
if "progress" not in st.session_state:
    st.session_state.progress = 0
if "last_section" not in st.session_state:
    st.session_state.last_section = ""
if "is_generating" not in st.session_state:
    st.session_state.is_generating = False

# Quick guide before goal input
st.info("""
**Quick Guide:**
1. Enter a clear learning goal, for example:
    - "I want to learn python basics in 3 days"
    - "I want to learn data science basics in 10 days"
2. Click **Generate Learning Path** to build your personalized day-wise plan
3. Review curated YouTube videos and resources in your learning path below
""")

# Main content area
st.header("Enter Your Goal")
user_goal = st.text_input(
    "Enter your learning goal:",
    help="Describe what you want to learn, and we'll generate a structured path using curated YouTube resources.",
)

# Progress area
progress_container = st.container()
progress_bar = st.empty()


def update_progress(message: str):
    """Update progress in the Streamlit UI"""
    st.session_state.current_step = message

    # Map backend progress messages to the original section/progress flow
    if "Preparing your learning path" in message or "Setting up agent" in message:
        section = "Setup"
        st.session_state.progress = 0.1
    elif "Connecting to learning resources" in message or "Loading available resources" in message:
        section = "Integration"
        st.session_state.progress = 0.2
    elif "Starting AI assistant" in message or "Ready to build" in message or "Creating AI agent" in message:
        section = "Setup"
        st.session_state.progress = 0.3
    elif "Researching videos" in message or "Generating your learning path" in message:
        section = "Generation"
        st.session_state.progress = 0.5
    elif "Finalizing your learning path" in message:
        section = "Generation"
        st.session_state.progress = 0.8
    elif "Learning path generation complete" in message:
        section = "Complete"
        st.session_state.progress = 1.0
        st.session_state.is_generating = False
    else:
        section = st.session_state.last_section or "Progress"

    st.session_state.last_section = section

    # Show progress bar
    progress_bar.progress(st.session_state.progress)

    # Update progress container with current status
    with progress_container:
        # Show section header if it changed
        if section != st.session_state.last_section and section != "Complete":
            st.write(f"**{section}**")

        # Show message with tick for completed steps
        if message == "Learning path generation complete!":
            st.success("All steps completed! 🎉")
        else:
            prefix = "✓" if st.session_state.progress >= 0.5 else "→"
            st.write(f"{prefix} {message}")


# Generate Learning Path button
if st.button("Generate Learning Path", type="primary", disabled=st.session_state.is_generating):
    if not user_goal:
        st.warning("Please enter your learning goal.")
    else:
        try:
            st.session_state.is_generating = True

            # Reset progress
            st.session_state.current_step = ""
            st.session_state.progress = 0
            st.session_state.last_section = ""

            learning_path = run_agent_sync(
                user_goal=user_goal,
                progress_callback=update_progress,
            )

            update_progress("Learning path generation complete!")

            # Display results
            st.header("Your Learning Path")
            if learning_path:
                st.markdown(learning_path)
            else:
                st.error("No results were generated. Please try again.")
                st.session_state.is_generating = False
        except ConfigurationError as e:
            st.error(str(e))
            st.session_state.is_generating = False
        except AgentTimeoutError as e:
            st.error(str(e))
            st.session_state.is_generating = False
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            st.error(
                "Please try again. If the problem persists, ensure the learning "
                "resource service is available."
            )
            st.session_state.is_generating = False
