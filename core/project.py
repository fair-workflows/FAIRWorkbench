"""
Project module contains all functions related to loading project files and metadata.
"""

from pathlib import Path
from typing import Union, Dict

import yaml

from config import CWL_WORKFLOW_DIR, PYTHON_DIR


def _load_workflow(project_path: Union[str, Path]):
    """
    Loads "generic" implementation of the workflow. Right now this representation is based on the cwl data.

    :param project_path:
    :return:
    """
    project_path = Path(project_path)
    workflow_path = project_path / CWL_WORKFLOW_DIR

    # Assuming the workflow directory has only one file
    workflow_file = next(workflow_path.iterdir())
    workflow_file = str(workflow_file)

    with open(workflow_file, 'r') as f:
        wf = yaml.load(f)

    return wf


def get_step_code(project_path, step_name):
    project_path = Path(project_path)
    steps_path = project_path/ PYTHON_DIR

    step_file = steps_path / f'{step_name}.py'

    return step_file.read_text()


def get_steps(project_path: str) -> Dict[str, any]:
    """
    Get description of the steps in the workflow. For now these descriptions are based on cwl.
    :param project_path:
    :return:
    """
    wf = _load_workflow(project_path)
    return wf['steps']