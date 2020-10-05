import inspect
import time
import warnings
from typing import List, Tuple
from urllib.parse import urldefrag

import rdflib
from rdflib import RDF, DCTERMS, DC

from .nanopub import Nanopub
from .rdf_wrapper import RdfWrapper

FAIRSTEP_PREDICATES = [RDF.type, Nanopub.PPLAN.hasInputVar,
                       Nanopub.PPLAN.hasOutputVar, DCTERMS.description]


class FairStep(RdfWrapper):
    """Represent a step in a fair workflow.

    Class for building, validating and publishing Fair Steps,
    as described by the plex ontology in the publication:
    Celebi, R., Moreira, J. R., Hassan, A. A., Ayyar, S., Ridder, L., Kuhn, T.,
    & Dumontier, M. (2019). Towards FAIR protocols and workflows: T
    he OpenPREDICT case study. arXiv preprint arXiv:1911.09531.

    Fair Steps may be fetched from Nanopublications, created from rdflib
    graphs or python functions.
    """

    def __init__(self, uri=None):
        super().__init__(uri=uri, ref_name='step')

    @classmethod
    def from_rdf(cls, rdf, uri=None):
        """Construct Fair Step from existing RDF."""
        self = cls(uri)
        self._rdf = rdf
        if rdflib.URIRef(self._uri) not in rdf.subjects():
            warnings.warn(f"Warning: Provided URI '{self._uri}' does not "
                          f"match any subject in provided rdf graph.")
        self.anonymise_rdf()
        return self

    @classmethod
    def from_nanopub(cls, uri):
        """
            Fetches the nanopublication corresponding to the specified URI, and attempts to extract the rdf describing a fairstep from
            its assertion graph. If the URI passed to this function is the uri of the nanopublication (and not the step itself) then
            an attempt will be made to identify what the URI of the step actually is, by checking if the nanopub npx:introduces a
            particular concept.

            If the assertion graph does not contain any triples with the step URI as subject, an exception is raised. If such triples
            are found, then ALL triples in the assertion are added to the rdf graph for this FairStep.
        """
        # Work out the nanopub URI by defragging the step URI
        nanopub_uri, frag = urldefrag(uri)

        # Fetch the nanopub
        np = Nanopub.fetch(nanopub_uri)

        # If there was no fragment in the original uri, then the uri was already the nanopub one.
        # Try to work out what the step's URI is, by looking at what the np is introducing.
        if len(frag) == 0:
            concepts_introduced = []
            for s, p, o in np.pubinfo.triples((None, Nanopub.NPX.introduces, None)):
                concepts_introduced.append(o)

            if len(concepts_introduced) == 0:
                raise ValueError('This nanopub does not introduce any concepts. Please provide URI to the step itself (not just the nanopub).')
            elif len(concepts_introduced) > 0:
                step_uri = str(concepts_introduced[0])

            print('Assuming step URI is', step_uri)

        else:
            step_uri = uri
        self = cls(uri=step_uri)

        # Check that the nanopub's assertion actually contains triples refering to the given step's uri
        if (rdflib.URIRef(self._uri), None, None) not in np.assertion:
            raise ValueError(f'No triples pertaining to the specified step (uri={step_uri}) were found in the assertion graph of the corresponding nanopublication (uri={nanopub_uri})')

        # Else extract all triples in the assertion into the rdf graph for this step
        self._rdf += np.assertion

        # Record that this RDF originates from a published source
        self._is_published = True

        self.anonymise_rdf()
        return self

    @classmethod
    def from_function(cls, function):
        """
            Generates a plex rdf decription for the given python function, and makes this FairStep object a bpmn:ScriptTask.
        """
        name = function.__name__ + str(time.time())
        uri = 'http://purl.org/temp/function' + name
        self = cls(uri=uri)
        code = inspect.getsource(function)

        # Set description of step to the raw function code
        self.description = code

        # Specify that step is a pplan:Step
        self.set_attribute(RDF.type, Nanopub.PPLAN.Step, overwrite=False)

        # Specify that step is a ScriptTask
        self.set_attribute(RDF.type, Nanopub.BPMN.ScriptTask, overwrite=False)

        # Get the input params for this function
        arginfo = inspect.getfullargspec(function)

        # Check that all variables provided have been given types
        inputs = {}
        for arg in arginfo.args:
            if arg not in arginfo.annotations:
                raise ValueError(f'Argument {arg} does not have a type annotation.')
            else:
                inputs[arg] = arginfo.annotations[arg]

        # Check that return type is explicitly stated
        if 'return' not in arginfo.annotations:
            raise ValueError(f'Function does not have a return type specified')
        else:
            return_type = arginfo.annotations['return']

        # Make URIs for the inputs and (if applicable) output.
        # Use these to set the inputs/outputs of the step.
        input_list = [uri + '/' + varname for varname in inputs]
        self.inputs = input_list

        # TODO: Setting types should probably be possible using the .inputs property setter? Or better idea?
        for varname, vartype in inputs.items():
            varuri = uri + '/' + varname
            self._rdf.add( (rdflib.URIRef(varuri), Nanopub.PROV.entity, rdflib.term.Literal(vartype)) )

        if return_type:
            varuri = uri + '/return'
            self.outputs = [varuri] 
            self._rdf.add( (rdflib.URIRef(varuri), Nanopub.PROV.entity, rdflib.term.Literal(return_type)) )

        # Specify that the language is python
        self.set_attribute(DC.language, rdflib.URIRef('python'), overwrite=False)
        return self

    @property
    def is_pplan_step(self):
        """Return True if this FairStep is a pplan:Step, else False."""
        return (self.self_ref, RDF.type, Nanopub.PPLAN.Step) in self._rdf

    @property
    def is_manual_task(self):
        """Returns True if this FairStep is a bpmn:ManualTask, else False."""
        return (self.self_ref, RDF.type, Nanopub.BPMN.ManualTask) in self._rdf

    @property
    def is_script_task(self):
        """Returns True if this FairStep is a bpmn:ScriptTask, else False."""
        return (self.self_ref, RDF.type, Nanopub.BPMN.ScriptTask) in self._rdf

    @property
    def inputs(self) -> List[rdflib.URIRef]:
        """Inputs for this step.

        Inputs are a list of URIRef's. The URIs should point to
        a pplan.Variable, for example: www.purl.org/stepuri#inputvarname.
        Set inputs by passing a list of strings depicting URIs. This
        overwrites old inputs.
        """
        return self.get_attribute(Nanopub.PPLAN.hasInputVar,
                                  return_list=True)

    @inputs.setter
    def inputs(self, uris: List[str]):
        self.remove_attribute(Nanopub.PPLAN.hasInputVar)
        for uri in uris:
            self.set_attribute(Nanopub.PPLAN.hasInputVar, rdflib.URIRef(uri),
                               overwrite=False)

    @property
    def outputs(self) -> List[rdflib.URIRef]:
        """Get outputs for this step.

        Outputs are a list of URIRef's. The URIs should point to
        a pplan.Variable, for example: www.purl.org/stepuri#outputvarname.
        Set outputs by passing a list of strings depicting URIs. This
        overwrites old outputs.
        """
        return self.get_attribute(Nanopub.PPLAN.hasOutputVar,
                                  return_list=True)

    @outputs.setter
    def outputs(self, uris: List[str]):
        self.remove_attribute(Nanopub.PPLAN.hasOutputVar)
        for uri in uris:
            self.set_attribute(Nanopub.PPLAN.hasOutputVar, rdflib.URIRef(uri),
                               overwrite=False)

    @property
    def description(self):
        """Description.

        Returns the dcterms:description of this step (or a list, if more than
        one matching triple is found)
        """
        return self.get_attribute(DCTERMS.description)

    @description.setter
    def description(self, value):
        """
        Adds the given text string as a dcterms:description for this FairStep
        object.
        """
        self.set_attribute(DCTERMS.description, rdflib.term.Literal(value))

    def validate(self):
        """Validate step.

        Check whether this step rdf has sufficient information required of
        a step in the Plex ontology.
        """
        conforms = True
        log = ''

        if not self.is_pplan_step:
            log += 'Step RDF does not say it is a pplan:Step\n'
            conforms = False

        if not self.description:
            log += 'Step RDF has no dcterms:description\n'
            conforms = False

        if self.is_manual_task == self.is_script_task:
            log += 'Step RDF must be either a bpmn:ManualTask or a bpmn:ScriptTask\n'
            conforms = False

        assert conforms, log


    def execute(self, *args: Tuple[str, str], log=True, agent=None):

        # Build input dict from the var/value tuples provided. Check that no vars are assigned twice,
        # and that all vars are recognised inputs to this step.
        input_dict = {}
        for var, value in args:
            var = rdflib.URIRef(var)

            if var not in self.inputs:
                raise Exception(f'{var} is not a recognized input variable of this step.')
            if var in input_dict:
                raise Exception(f'Variable {var} cannot be specified more than once in argument list to .execute()')

            input_dict[var] = value

            if log:
                print(f'Input variable {var} was assigned value: {value}')

        # Check that values for all input vars have been assigned
        for var in self.inputs:
            if var not in input_dict:
                raise Exception(f'Input variable {var} needs to be assigned a value.')


        # Generate execution prov
        prov = rdflib.Graph()

        this_step = rdflib.Namespace(self._uri)
        this_activity = this_step.activity

        print( (this_activity, Nanopub.PPLAN.correspondsToStep, this_step) )

        # For manual tasks, the agent carrying out the task must be specified
        if self.is_manual_task:
            if agent is None:
                raise Exception('For manual tasks, the "agent" must be specified to FairStep execute() method. This should be a URI indicating the entity that carried out the task.')

        elif self.is_script_task:
            function_code = self.description
            if str(self.get_attribute(DC.language)) == 'python':
                print(f'Execute function f{function_code}, with inputs f{input_dict}')
            else:
                raise Exception('Only python is currently supported as a software language')


        print( (this_step, Nanopub.PROV.wasAssociatedWith, agent) )

        for var, value in input_dict.items():
            print( (var, Nanopub.PROV.value, value) )
    


    def __str__(self):
        """
            Returns string representation of this FairStep object.
        """
        s = f'Step URI = {self._uri}\n'
        s += self._rdf.serialize(format='trig').decode('utf-8')
        return s
