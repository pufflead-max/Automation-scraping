from airflow.models import DagRun
from airflow.utils.state import State
from airflow.api.common.trigger_dag import trigger_dag
from datetime import datetime

def trigger_cookie_rotation(context):
    """
    Callback to trigger the cookie rotation DAG strictly on authentication or session failure.
    """
    exception = context.get('exception')
    error_msg = str(exception).lower() if exception else ""
    
    # Define keywords that indicate authentication or session issues
    auth_failure_triggers = [
        "authentication failed",
        "session invalid",
        "cookies likely expired",
        "login wall detected",
        "redirected to login",
        "update cookies in airflow variables"
    ]
    
    # Only trigger if this looks like a session/auth issue
    is_auth_failure = any(trigger in error_msg for trigger in auth_failure_triggers)
    
    if not is_auth_failure:
        print(f"Task failure detected in {context['task_instance'].task_id}, but it does not appear to be an auth issue. Skipping auto-rotation.")
        print(f"Error message was: {error_msg}")
        return

    # Determine which rotation DAG to trigger
    target_dag_id = None
    if "facebook" in context['dag'].dag_id.lower():
        target_dag_id = 'facebook_cookie_rotation_dag'
    elif "nextdoor" in context['dag'].dag_id.lower():
        target_dag_id = 'nextdoor_cookie_rotation_dag'

    if not target_dag_id:
        print(f"No specific rotation DAG found for {context['dag'].dag_id}. Skipping.")
        return

    run_id = f"triggered_by_auth_failure_{context['dag'].dag_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"!!! Authentication failure detected in {context['dag'].dag_id}. Triggering {target_dag_id} !!!")
    
    try:
        trigger_dag(
            dag_id=target_dag_id,
            run_id=run_id,
            conf={
                'triggered_by': context['dag'].dag_id, 
                'reason': 'auth_failure'
            },
            replace_microseconds=False
        )
    except Exception as e:
        print(f"Failed to trigger cookie rotation DAG: {e}")
