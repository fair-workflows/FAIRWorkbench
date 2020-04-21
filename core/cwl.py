from pathlib import Path
from typing import List, Union, Dict

import cwlgen
from scriptcwl import WorkflowGenerator

DEFAULT_TYPE = 'int'
STEPS_DIR = 'steps'
WORKFLOW_DIR = 'workflow'


def create_workflow(name, steps, cwl_dir):
    # TODO: Right now all steps will be brand new. In the future it should be possible to specify existing steps
    cwl_dir = Path(cwl_dir)
    steps_path = cwl_dir / STEPS_DIR
    workflow_path = cwl_dir / WORKFLOW_DIR

    steps_path.mkdir()
    workflow_path.mkdir()

    # Create commandlinetool for every step
    for step in steps:
        tool_object = create_commandlinetool(step)
        tool_object.export(steps_path / f'{step["name"]}.cwl')

    with WorkflowGenerator() as wf:
        wf.load(steps_path)

        # TODO: Replace use of default type with actual specified type
        # Input to the first step is the input to the workflow
        first_step = steps[0]
        inputs = {f'{first_step["name"]}/{name}': wf.add_input(**{name: DEFAULT_TYPE}) for name in first_step['input']}

        for step in steps:
            step_func = wf.__getattr__(step['name'])
            inputs = step_func(**inputs)

        # The following will fail
        wf.add_outputs()

        filepath = workflow_path / f'{name}.cwl'

        wf.save(filepath)

        return filepath


def create_commandlinetool(step: Dict[str, Union[str, List]]) -> cwlgen.CommandLineTool:
    name = step['name']
    description = step['description']

    # Initialize commandlinetool
    # TODO: Specify path
    tool_object = cwlgen.CommandLineTool(tool_id=name,
                                         base_command=f"./{name}.py",
                                         doc=description,
                                         cwl_version="v1.0")

    # Specify input parameters
    tool_object.inputs += [cwlgen.CommandInputParameter(p, param_type=DEFAULT_TYPE) for p in step['input']]

    # Specify output parameters
    tool_object.outputs += [cwlgen.CommandInputParameter(p, param_type=DEFAULT_TYPE) for p in step['output']]

    return tool_object