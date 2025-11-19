import streamlit as st
import asyncio
from strands_cli.api import Workflow
from strands_cli.types import Spec, Pattern, PatternType, PatternConfig, Runtime, ProviderType, WorkflowTask, Agent

# Configure page
st.set_page_config(page_title="Strands Workflow Demo", layout="wide")
st.title("Strands Workflow Demo")

# Define a simple workflow spec
@st.cache_resource
def get_workflow():
    spec = Spec(
        name="streamlit_demo",
        runtime=Runtime(provider=ProviderType.OPENAI, model_id="gpt-5-nano"),
        agents={
            "greeter": Agent(prompt="You are a helpful greeter. Say hello to the user."),
            "analyst": Agent(prompt="You are an analyst. Analyze the user's input.")
        },
        pattern=Pattern(
            type=PatternType.WORKFLOW,
            config=PatternConfig(
                tasks=[
                    WorkflowTask(id="greet", agent="greeter", description="Greet the user"),
                    WorkflowTask(
                        id="ask_name", 
                        type="hitl", 
                        prompt="What is your name?", 
                        deps=["greet"]
                    ),
                    WorkflowTask(
                        id="analyze", 
                        agent="analyst", 
                        description="Analyze the name",
                        input="Analyze the name: {{ tasks.ask_name.response }}",
                        deps=["ask_name"]
                    )
                ]
            )
        )
    )
    return Workflow(spec)

workflow = get_workflow()

# Session State Management
if "session_id" not in st.session_state:
    st.session_state.session_id = None

if "workflow_session" not in st.session_state:
    st.session_state.workflow_session = None

# Sidebar controls
with st.sidebar:
    st.header("Controls")
    if st.button("Start New Workflow"):
        # Create new session
        session = workflow.create_session()
        session.start()
        st.session_state.session_id = session.session_id
        st.session_state.workflow_session = session
        st.rerun()

    if st.button("Reset"):
        st.session_state.session_id = None
        st.session_state.workflow_session = None
        st.rerun()

# Main Display
if st.session_state.workflow_session:
    session = st.session_state.workflow_session
    
    st.subheader(f"Session: {session.session_id}")
    st.text(f"State: {session.state.value}")
    
    # Display Progress
    # Note: In a real app, you'd poll or use a callback to update UI
    # For this demo, we rely on manual reruns or interaction
    
    if session.is_paused():
        hitl_state = session.get_hitl_state()
        if hitl_state:
            st.info(f"Workflow Paused: {hitl_state.prompt}")
            
            with st.form("hitl_form"):
                user_input = st.text_input("Your Response")
                submitted = st.form_submit_button("Submit")
                
                if submitted:
                    session.resume(user_input)
                    st.success("Resumed! Rerunning...")
                    st.rerun()
    
    elif session.is_complete():
        st.success("Workflow Completed!")
        result = session.get_result()
        st.json(result.model_dump())
        
    elif session.is_failed():
        st.error(f"Workflow Failed: {session.get_error()}")
        
    elif session.is_running():
        st.spinner("Workflow is running...")
        # Auto-refresh to check status
        asyncio.run(asyncio.sleep(1))
        st.rerun()

else:
    st.info("Click 'Start New Workflow' to begin.")
