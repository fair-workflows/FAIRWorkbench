import inspect
import time
from copy import deepcopy
from typing import List

import rdflib
from rdflib import RDF, RDFS, DCTERMS

from fairworkflows import namespaces
from fairworkflows.rdf_wrapper import RdfWrapper

FAIRSTEP_PREDICATES = [RDF.type, namespaces.PPLAN.hasInputVar,
                       namespaces.PPLAN.hasOutputVar, DCTERMS.description, RDFS.label]


class FairVariable:
    def __init__(self, name: str = None, type: str = None):
        self.name = name
        self.type = type

    def __eq__(self, other):
        return self.name == other.name and self.type == other.type

    def __hash__(self):
        return hash(str(self))

    def __str__(self):
        return f'FairVariable {self.name} of type: {self.type}'


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

    def __init__(self, label: str = None, description: str = None, uri=None,
                 is_pplan_step: bool = True, is_manual_task: bool = None,
                 is_script_task: bool = None, inputs: List[FairVariable] = None,
                 outputs: List[FairVariable] = None):
        super().__init__(uri=uri, ref_name='step')
        self.label = label
        self.description = description
        self.is_pplan_step = is_pplan_step
        if is_script_task and is_manual_task:
            ValueError('A fair step cannot be both a manual and a script task, at least one of'
                       'is_fair_step and is_script_task must be False')
        self.is_manual_task = is_manual_task
        self.is_script_task = is_script_task
        if inputs is not None:
            self.inputs = inputs
        if outputs is not None:
            self.outputs = outputs
        self._is_modified = False

    @classmethod
    def from_rdf(cls, rdf, uri, fetch_references: bool = False, force: bool = False,
                 remove_irrelevant_triples: bool = True):
        """Construct Fair Step from existing RDF.

        Args:
            rdf: The RDF graph
            uri: Uri of the object
            fetch_references: Boolean toggling whether to fetch objects from nanopub that are
                referred by this object. For a FairStep there are currently no references supported.
            force: Toggle forcing creation of object even if url is not in any of the subjects of
                the passed RDF
            remove_irrelevant_triples: Toggle removing irrelevant triples for this Step. This
                uses heuristics that might not work for all passed RDF graphs.
        """
        cls._uri_is_subject_in_rdf(uri, rdf, force=force)
        self = cls(uri=uri)
        if remove_irrelevant_triples:
            self._rdf = self._get_relevant_triples(uri, rdf)
        else:
            self._rdf = deepcopy(rdf)  # Make sure we don't mutate user RDF
        self.anonymise_rdf()
        return self

    @staticmethod
    def _get_relevant_triples(uri, rdf):
        """
        Select only relevant triples from RDF using the following heuristics:
        * Match all triples that are through an arbitrary-length property path related to the
            step uri. So if 'URI predicate Something', then all triples 'Something predicate
            object' are selected, and so forth.
        * Filter out the DUL:precedes predicate triples, because they are part of a workflow and
            not of a step.

        """
        q = """
        PREFIX dul: <http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#>
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            # Match all triples that are through an arbitrary-length property path related to the
            # step uri. (a|!a) matches all predicates. Binding to step_uri is done when executing.
            ?step_uri (a|!a)+ ?o .
            # Filter out precedes relations
            ?s !dul:precedes ?o .
        }
        """
        g = rdflib.Graph(namespace_manager=rdf.namespace_manager)
        for triple in rdf.query(q, initBindings={'step_uri': rdflib.URIRef(uri)}):
            g.add(triple)
        return g

    @classmethod
    def from_function(cls, function):
        """
            Generates a plex rdf decription for the given python function, and makes this FairStep object a bpmn:ScriptTask.
        """
        name = function.__name__ + str(time.time())
        uri = 'http://purl.org/nanopub/temp/mynanopub#function' + name
        code = inspect.getsource(function)
        return cls(label=function.__name__, description=code, uri=uri, is_pplan_step=True,
                   is_script_task=True)

    @property
    def is_pplan_step(self):
        """Return True if this FairStep is a pplan:Step, else False."""
        return (self.self_ref, RDF.type, namespaces.PPLAN.Step) in self._rdf

    @is_pplan_step.setter
    def is_pplan_step(self, value: bool):
        """
        Adds/removes the pplan:Step triple from the RDF, in accordance with the provided boolean.
        """
        if value:
            if not self.is_pplan_step:
                self.set_attribute(RDF.type, namespaces.PPLAN.Step, overwrite=False)
        else:
            self.remove_attribute(RDF.type, object=namespaces.PPLAN.Step)

    @property
    def is_manual_task(self):
        """Returns True if this FairStep is a bpmn:ManualTask, else False."""
        return (self.self_ref, RDF.type, namespaces.BPMN.ManualTask) in self._rdf

    @is_manual_task.setter
    def is_manual_task(self, value: bool):
        """
        Adds/removes the manual task triple to the RDF, in accordance with the provided boolean.
        """
        if value:
            if not self.is_manual_task:
                self.set_attribute(RDF.type, namespaces.BPMN.ManualTask, overwrite=False)
            self.is_script_task = False  # manual and script are mutually exclusive
        else:
            self.remove_attribute(RDF.type, object=namespaces.BPMN.ManualTask)

    @property
    def is_script_task(self):
        """Returns True if this FairStep is a bpmn:ScriptTask, else False."""
        return (self.self_ref, RDF.type, namespaces.BPMN.ScriptTask) in self._rdf

    @is_script_task.setter
    def is_script_task(self, value: bool):
        """
        Adds/removes the script task triple to the RDF, in accordance with the provided boolean.
        """
        if value:
            if not self.is_script_task:
                self.set_attribute(RDF.type, namespaces.BPMN.ScriptTask, overwrite=False)
            self.is_manual_task = False  # manual and script are mutually exclusive
        else:
            self.remove_attribute(RDF.type, object=namespaces.BPMN.ScriptTask)

    def _get_variable(self, var_ref: rdflib.term.BNode) -> FairVariable:
        """Retrieve a specific FairVariable from the RDF triples."""
        var_types = self._rdf.objects(var_ref, RDF.type)
        var_type = [var_type for var_type in var_types
                    if isinstance(var_type, rdflib.term.Literal)][0]
        return FairVariable(name=str(var_ref),
                            type=str(var_type))

    def _add_variable(self, variable: FairVariable, relation_to_step):
        """Add triples describing FairVariable to rdf."""
        var_ref = rdflib.term.BNode(variable.name)
        self.set_attribute(relation_to_step, var_ref, overwrite=False)
        self._rdf.add((var_ref, RDF.type, rdflib.term.Literal(variable.type)))
        self._rdf.add((var_ref, RDF.type, namespaces.PPLAN.Variable))

    @property
    def inputs(self) -> List[FairVariable]:
        """Inputs for this step.

        Inputs are a list of FairVariable objects. They correspond to triples in the RDF:
        The name is stored as a blanknode with a hasInPutVar relation to the step.
        This blanknode has type pplan:Variable and a string literal referring to the type of the
        variable.
        """
        return [self._get_variable(var_ref) for var_ref
                in self.get_attribute(namespaces.PPLAN.hasInputVar, return_list=True)]

    @inputs.setter
    def inputs(self, variables: List[FairVariable]):
        self.remove_attribute(namespaces.PPLAN.hasInputVar)
        for variable in variables:
            self._add_variable(variable, namespaces.PPLAN.hasInputVar)

    @property
    def outputs(self) -> List[FairVariable]:
        """Outputs for this step.

        Outputs are a list of URIRef's. The URIs should point to
        a pplan.Variable, for example: www.purl.org/stepuri#outputvarname.
        Set outputs by passing a list of strings depicting URIs. This
        overwrites old outputs.
        """
        return [self._get_variable(var_ref) for var_ref
                in self.get_attribute(namespaces.PPLAN.hasOutputVar, return_list=True)]

    @outputs.setter
    def outputs(self, variables: List[FairVariable]):
        self.remove_attribute(namespaces.PPLAN.hasOutputVar)
        for variable in variables:
            self._add_variable(variable, namespaces.PPLAN.hasOutputVar)

    @property
    def label(self):
        """Label.

        Returns the rdfs:label of this step (or a list, if more than one matching triple is found)
        """
        return self.get_attribute(RDFS.label)

    @label.setter
    def label(self, value):
        """
        Adds the given text string as an rdfs:label for this FairStep
        object.
        """
        self.set_attribute(RDFS.label, rdflib.term.Literal(value))

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

    def validate(self, shacl=False):
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

        if not self.label:
            log += 'Step RDF has no rdfs:label\n'
            conforms = False

        if self.is_manual_task == self.is_script_task:
            log += 'Step RDF must be either a bpmn:ManualTask or a bpmn:ScriptTask\n'
            conforms = False

        assert conforms, log

        # Now validate against the PLEX shacl shapes file, if requested
        if shacl:
            self.shacl_validate()

    def publish_as_nanopub(self, use_test_server=False, **kwargs):
        """
        Publish this rdf as a nanopublication.

        Args:
            use_test_server (bool): Toggle using the test nanopub server.
            kwargs: Keyword arguments to be passed to [nanopub.Publication.from_assertion](
                https://nanopub.readthedocs.io/en/latest/reference/publication.html#
                nanopub.publication.Publication.from_assertion).
                This allows for more control over the nanopublication RDF.

        Returns:
            a dictionary with publication info, including 'nanopub_uri', and 'concept_uri'
        """
        return self._publish_as_nanopub(use_test_server=use_test_server, **kwargs)

    def __str__(self):
        """
            Returns string representation of this FairStep object.
        """
        s = f'Step URI = {self._uri}\n'
        s += self._rdf.serialize(format='trig').decode('utf-8')
        return s


def mark_as_fairstep(label: str = None, is_pplan_step: bool = True, is_manual_task: bool = None,
                     is_script_task: bool = None):
    def modify_function(func):
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        # Description of step is the raw function code
        description = inspect.getsource(func)
        argspec = inspect.getfullargspec(func)
        inputs = [FairVariable(name=arg, type=argspec.annotations[arg].__name__)
                  for arg in argspec.args]
        output = FairVariable(name=func.__name__ + '_output',
                              type=argspec.annotations['return'].__name__)

        wrapper._fairstep = FairStep(label=label,
                                     description=description,
                                     is_pplan_step=is_pplan_step,
                                     is_manual_task=is_manual_task,
                                     is_script_task=is_script_task,
                                     inputs=inputs,
                                     outputs=[output]
                                     )
        return wrapper
    return modify_function
