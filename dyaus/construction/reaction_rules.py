import sys
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, NamedTuple, Optional

import numpy as np

from .prepositions import PREPOSITIONS


class Protein(NamedTuple):
    unphosphorylated: str
    phosphorylated: str


class UnregisteredRule(NamedTuple):
    expected: Optional[str]
    original: Optional[str]


@dataclass
class ReactionRules(object):
    """Create an executable ODE model from a text file.

    reaction | kinetic constants | initial conditions

    Attributes
    ----------
    * input_txt : str
        Model description file (*.txt), e.g., 'Kholodenko_JBC_1999.txt'

    * parameters : list of strings
        x : model parameters.

    * species : list of strings
        y : model species.

    * reactions : list of strings
        v : flux vector.

    * differential_equations : list of strings
        dydt : right-hand side of the differential equation.

    * obs_desc : list of List[str]
        Description of observables.

    * param_info : list of strings
        Information about parameter values.

    * init_info : list of strings
        Information about initial values.

    * param_constraints : list of strings
        Information about parameter constraints.

    * param_excluded : list of strings
        Parameters excluded from search params because of parameter constraints.

    * protein_phosphorylation : list of NamedTuples
        Pairs of unphosphorylated and phosphorylated proteins.

    * sim_tspan : list of strings ['t0', 'tf']
        Interval of integration.

    * sim_conditions : list of List[str]
        Simulation conditions with stimulation.

    * sim_unperturbed : str
        Untreated conditions to get steady state.

    * rule_words : dict
        Words to identify reaction rules.

    """

    input_txt: str

    parameters: List[str] = field(
        default_factory=list,
        init=False,
    )
    species: List[str] = field(
        default_factory=list,
        init=False,
    )
    reactions: List[str] = field(
        default_factory=list,
        init=False,
    )
    differential_equations: List[str] = field(
        default_factory=list,
        init=False,
    )
    obs_desc: List[List[str]] = field(
        default_factory=list,
        init=False,
    )
    param_info: List[str] = field(
        default_factory=list,
        init=False,
    )
    init_info: List[str] = field(
        default_factory=list,
        init=False,
    )
    param_constraints: List[str] = field(
        default_factory=list,
        init=False,
    )
    param_excluded: List[str] = field(
        default_factory=list,
        init=False,
    )
    # Detection of mistakes
    protein_phosphorylation: List[Protein] = field(
        default_factory=list,
        init=False,
    )
    # Information about simulation
    sim_tspan: List[str] = field(
        default_factory=list,
        init=False,
    )
    sim_conditions: List[List[str]] = field(
        default_factory=list,
        init=False,
    )
    sim_unperturbed: str = field(
        default_factory=str,
        init=False,
    )
    # Words to identify reaction rules
    rule_words: Dict[str, List[str]] = field(
        default_factory=lambda: dict(
            dimerize=[
                " dimerizes",
                " homodimerizes",
                " forms a dimer",
                " forms dimers",
            ],
            bind=[
                " binds",
                " forms complexes with",
            ],
            is_dissociated=[
                " is dissociated into",
            ],
            is_phosphorylated=[
                " is phosphorylated",
            ],
            is_dephosphorylated=[
                " is dephosphorylated",
            ],
            phosphorylate=[
                " phosphorylates",
            ],
            dephosphorylate=[
                " dephosphorylates",
            ],
            transcribe=[
                " transcribe",
                " transcribes",
            ],
            is_translated=[
                " is translated into",
            ],
            synthesize=[
                " synthesizes",
                " promotes synthesis of",
            ],
            is_synthesized=[
                " is synthesized",
            ],
            degrade=[
                " degrades",
                " promotes degradation of",
            ],
            is_degraded=[
                " is degraded",
            ],
            is_translocated=[
                " is translocated",
            ],
        ),
        init=False,
    )

    @staticmethod
    def _isfloat(string: str) -> bool:
        """
        Checking if a string can be converted to float.
        """
        try:
            float(string)
            return True
        except ValueError:
            return False

    def _set_params(self, line_num: int, *args: str) -> None:
        """
        Set model parameters.
        """
        for p_name in args:
            if not p_name + f"{line_num:d}" in self.parameters:
                self.parameters.append(p_name + f"{line_num:d}")

    def _set_species(self, *args: str) -> None:
        """
        Set model species.
        """
        for s_name in args:
            if s_name not in self.species:
                self.species.append(s_name)

    def _preprocessing(
        self,
        func_name: str,
        line_num: int,
        line: str,
        *args: str,
    ) -> List[str]:
        """
        Extract the information about parameter and/or initial values
        if '|' in the line and find a keyword to identify reaction rules.

        Parameters
        ----------
        func_name : str
            Name of the rule function.

        line_num : int
            Line number.

        line : str
            Each line of the input text.

        Returns
        -------
        description : list of strings

        """
        self._set_params(line_num, *args)
        if "|" in line:
            if line.split("|")[1].strip():
                param_values = line.split("|")[1].strip().split(",")
                if all("=" in pval for pval in param_values):
                    for pval in param_values:
                        base_param = pval.split("=")[0].strip(" ")
                        if base_param.startswith("const "):
                            # Parameter names with 'const' will be added to param_excluded.
                            base_param = base_param.split("const ")[-1]
                            fixed = True
                        else:
                            fixed = False
                        if base_param in args:
                            if self._isfloat(pval.split("=")[1].strip(" ")):
                                self.param_info.append(
                                    "x[C."
                                    + base_param
                                    + f"{line_num:d}] = "
                                    + pval.split("=")[1].strip(" ")
                                )
                                # If a parameter value is initialized to 0.0,
                                # then add it to param_excluded.
                                if float(pval.split("=")[1].strip(" ")) == 0.0 or fixed:
                                    self.param_excluded.append(base_param + f"{line_num:d}")
                            else:
                                raise ValueError(
                                    f"line{line_num:d}: Parameter value must be int or float."
                                )
                        else:
                            raise ValueError(
                                f"line{line_num:d}: '{pval.split('=')[0].strip(' ')}'\n"
                                f"Available parameters are: {', '.join(args)}."
                            )
                elif param_values[0].strip(" ").isdecimal():
                    # Parameter constraints
                    for param_name in args:
                        if f"{param_name}{int(param_values[0]):d}" not in self.parameters:
                            raise ValueError(
                                f"Line {line_num:d} and {int(param_values[0]):d} : "
                                "Different reaction rules in parameter constraints."
                            )
                        else:
                            self.param_excluded.append(f"{param_name}{line_num:d}")
                            self.param_info.append(
                                f"x[C.{param_name}"
                                f"{line_num:d}] = "
                                f"x[C.{param_name}"
                                f"{int(param_values[0]):d}]"
                            )
                            self.param_constraints.append(
                                f"x[C.{param_name}"
                                f"{line_num:d}] = "
                                f"x[C.{param_name}"
                                f"{int(param_values[0]):d}]"
                            )
            if line.count("|") > 1 and line.split("|")[2].strip():
                initial_values = line.split("|")[2].strip().split(",")
                for ival in initial_values:
                    if ival.split("=")[0].strip(" ") in line.split("|")[0]:
                        if self._isfloat(ival.split("=")[1].strip(" ")):
                            self.init_info.append(
                                "y0[V."
                                + ival.split("=")[0].strip(" ")
                                + "] = "
                                + ival.split("=")[1].strip(" ")
                            )
                        else:
                            raise ValueError(
                                f"line{line_num:d}: Initial value must be int or float."
                            )
                    else:
                        raise NameError(
                            f"line{line_num:d}: "
                            "Name'{ival.split('=')[0].strip(' ')}' is not defined."
                        )
            line = line.split("|")[0]
        hit_words: List[str] = []
        for word in self.rule_words[func_name]:
            # Choose longer word
            if word in line:
                hit_words.append(word)

        return line.strip().split(max(hit_words, key=len))

    @staticmethod
    def _word2scores(word: str, sentence: str) -> List[float]:
        """
        Calculate similarity scores between word and sentence.

        Parameters
        ----------
        word : str
            User-defined word.
        sentence : str
            Textual unit consisting of two or more words.

        returns
        -------
        ratio : list
            List containing similarity scores.

        """
        ratio = [
            SequenceMatcher(None, word, sentence[i : i + len(word)]).ratio()
            for i in range(len(sentence) - len(word) + 1)
        ]
        return ratio

    def _get_partial_similarity(
        self,
        line: str,
        similarity_threshold: float = 0.7,
    ) -> UnregisteredRule:
        """
        Suggest similar rule word when user-defined word is not registered
        in rule_words.

        Parameters
        ----------
        line : str
            Each line of the input text.

        similarity_threshold : float (default: 0.7)
            if all match_scores are below this value, expected_word will not
            be returned.

        Returns
        -------
        expected_word : str
            Rule word with the highest similarity score.

        """
        match_words = []
        match_scores = []
        str_subset = []
        for rules in self.rule_words.values():
            for word in rules:
                ratio = self._word2scores(word, line)
                if ratio:
                    match_words.append(word)
                    match_scores.append(max(ratio))
                    str_subset.append(line[np.argmax(ratio) : np.argmax(ratio) + len(word)])
        expected_word = (
            None
            if all([score < similarity_threshold for score in match_scores])
            else match_words[np.argmax(match_scores)]
        )
        original_word = (
            None if expected_word is None else str_subset[match_words.index(expected_word)]
        )

        return UnregisteredRule(expected_word, original_word)

    @staticmethod
    def _remove_prepositions(sentence: str) -> str:
        """
        Remove preposition from text not to use it to identify reaction rules.
        """
        for preposition in PREPOSITIONS:
            if sentence.endswith(preposition):
                return sentence.rstrip(preposition)
        else:
            return sentence

    def dimerize(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `monomer` + `monomer` <=> `dimer`

        Example
        -------
        `monomer` dimerizes --> `dimer`

        Rate equation
        -------------
        v = kf * [monomer] * [monomer] - kr * [dimer]

        Differential equation
        ---------------------
        d[monomer]/dt = - 2 * v
        d[dimer]/dt = + v

        """
        description = self._preprocessing(
            sys._getframe().f_code.co_name, line_num, line, "kf", "kr"
        )
        monomer = description[0].strip(" ")
        if " --> " in description[1]:
            dimer = description[1].split(" --> ")[1].strip(" ")
        else:
            raise ValueError(f"line{line_num:d}: Use '-->' to specify the name of the dimer.")
        if monomer == dimer:
            raise ValueError(f"{dimer} <- Use a different name.")
        self._set_species(monomer, dimer)
        self.reactions.append(
            f"v[{line_num:d}] = "
            f"x[C.kf{line_num:d}] * y[V.{monomer}] * y[V.{monomer}] - "
            f"x[C.kr{line_num:d}] * y[V.{dimer}]"
        )
        counter_monomer, counter_dimer = (0, 0)
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{monomer}]" in eq:
                counter_monomer += 1
                self.differential_equations[i] = eq + f" - 2 * v[{line_num:d}]"
            elif f"dydt[V.{dimer}]" in eq:
                counter_dimer += 1
                self.differential_equations[i] = eq + f" + v[{line_num:d}]"
        if counter_monomer == 0:
            self.differential_equations.append(f"dydt[V.{monomer}] = - v[{line_num:d}]")
        if counter_dimer == 0:
            self.differential_equations.append(f"dydt[V.{dimer}] = + v[{line_num:d}]")

    def bind(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `component1` + `component2` <=> `complex`

        Example
        -------
        `component1` binds `component2` --> `complex`

        Rate equation
        -------------
        v = kf * [component1] * [component2] - kr * [complex]

        Differential equation
        ---------------------
        d[component1]/dt = - v
        d[component2]/dt = - v
        d[complex]/dt = + v

        """
        description = self._preprocessing(
            sys._getframe().f_code.co_name, line_num, line, "kf", "kr"
        )
        component1 = description[0].strip(" ")
        if " --> " in description[1]:
            # Specify name of the complex
            component2 = description[1].split(" --> ")[0].strip(" ")
            complex = description[1].split(" --> ")[1].strip(" ")
        else:
            raise ValueError(
                f"line{line_num:d}: Use '-->' to specify the name of the protein complex."
            )
        if component1 == complex or component2 == complex:
            raise ValueError(f"line{line_num:d}: {complex} <- Use a different name.")
        elif component1 == component2:
            self.dimerize(line_num, line)
        else:
            self._set_species(component1, component2, complex)
            self.reactions.append(
                f"v[{line_num:d}] = "
                f"x[C.kf{line_num:d}] * y[V.{component1}] * y[V.{component2}] - "
                f"x[C.kr{line_num:d}] * y[V.{complex}]"
            )
            counter_component1, counter_component2, counter_complex = (0, 0, 0)
            for i, eq in enumerate(self.differential_equations):
                if f"dydt[V.{component1}]" in eq:
                    counter_component1 += 1
                    self.differential_equations[i] = eq + f" - v[{line_num:d}]"
                elif f"dydt[V.{component2}]" in eq:
                    counter_component2 += 1
                    self.differential_equations[i] = eq + f" - v[{line_num:d}]"
                elif f"dydt[V.{complex}]" in eq:
                    counter_complex += 1
                    self.differential_equations[i] = eq + f" + v[{line_num:d}]"
            if counter_component1 == 0:
                self.differential_equations.append(f"dydt[V.{component1}] = - v[{line_num:d}]")
            if counter_component2 == 0:
                self.differential_equations.append(f"dydt[V.{component2}] = - v[{line_num:d}]")
            if counter_complex == 0:
                self.differential_equations.append(f"dydt[V.{complex}] = + v[{line_num:d}]")

    def is_dissociated(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `complex` <=> `component1` + `component2`

        Examples
        --------
        `complex` is dissociated into `component1` and `component2`

        Rate equation
        -------------
        v = kf * [complex] - kr * [component1] * [component2]

        Differential equation
        ---------------------
        d[component1]/dt = + v
        d[component2]/dt = + v
        d[complex]/dt = - v

        """
        description = self._preprocessing(
            sys._getframe().f_code.co_name, line_num, line, "kf", "kr"
        )
        complex = description[0].strip(" ")
        if " and " not in description[1]:
            raise ValueError(
                f"Use 'and' in line{line_num:d}:\ne.g., AB is dissociated into A and B"
            )
        else:
            component1 = description[1].split(" and ")[0].strip(" ")
            component2 = description[1].split(" and ")[1].strip(" ")
        self._set_species(complex, component1, component2)
        self.reactions.append(
            f"v[{line_num:d}] = "
            f"x[C.kf{line_num:d}] * y[V.{complex}] - "
            f"x[C.kr{line_num:d}] * y[V.{component1}] * y[V.{component2}]"
        )
        counter_complex, counter_component1, counter_component2 = (0, 0, 0)
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{complex}]" in eq:
                counter_complex += 1
                self.differential_equations[i] = eq + f" - v[{line_num:d}]"
            elif f"dydt[V.{component1}]" in eq:
                counter_component1 += 1
                self.differential_equations[i] = (
                    eq + f" + v[{line_num:d}]"
                    if component1 != component2
                    else eq + f" + 2 * v[{line_num:d}]"
                )
            elif f"dydt[V.{component2}]" in eq:
                counter_component2 += 1
                self.differential_equations[i] = eq + f" + v[{line_num:d}]"
        if counter_complex == 0:
            self.differential_equations.append(f"dydt[V.{complex}] = - v[{line_num:d}]")
        if counter_component1 == 0:
            self.differential_equations.append(f"dydt[V.{component1}] = + v[{line_num:d}]")
        if counter_component2 == 0:
            self.differential_equations.append(f"dydt[V.{component2}] = + v[{line_num:d}]")

    def is_phosphorylated(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `unphosphorylated_form` <=> `phosphorylated_form`

        Examples
        --------
        `unphosphorylated_form` is phosphorylated --> `phosphorylated_form`

        Rate equation
        -------------
        v = kf * [unphosphorylated_form] - kr * [phosphorylated_form]

        Differential equation
        ---------------------
        d[unphosphorylated_form]/dt = - v
        d[phosphorylated_form]/dt = + v

        """
        description = self._preprocessing(
            sys._getframe().f_code.co_name, line_num, line, "kf", "kr"
        )
        unphosphorylated_form = description[0].strip(" ")
        if " --> " in description[1]:
            phosphorylated_form = description[1].split(" --> ")[1].strip(" ")
        else:
            raise ValueError(
                f"line{line_num:d}: "
                "Use '-->' to specify the name of the phosphorylated protein."
            )
        self._set_species(unphosphorylated_form, phosphorylated_form)
        self.protein_phosphorylation.append(Protein(unphosphorylated_form, phosphorylated_form))
        self.reactions.append(
            f"v[{line_num:d}] = "
            f"x[C.kf{line_num:d}] * y[V.{unphosphorylated_form}] - "
            f"x[C.kr{line_num:d}] * y[V.{phosphorylated_form}]"
        )
        counter_unphosphorylated_form, counter_phosphorylated_form = (0, 0)
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{unphosphorylated_form}]" in eq:
                counter_unphosphorylated_form += 1
                self.differential_equations[i] = eq + f" - v[{line_num:d}]"
            elif "dydt[V.{phosphorylated_form}]" in eq:
                counter_phosphorylated_form += 1
                self.differential_equations[i] = eq + f" + v[{line_num:d}]"
        if counter_unphosphorylated_form == 0:
            self.differential_equations.append(
                f"dydt[V.{unphosphorylated_form}] = - v[{line_num:d}]"
            )
        if counter_phosphorylated_form == 0:
            self.differential_equations.append(
                f"dydt[V.{phosphorylated_form}] = + v[{line_num:d}]"
            )

    def is_dephosphorylated(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `phosphorylated_form` --> `unphosphorylated_form`

        Example
        -------
        `phosphorylated_form` is dephosphorylated --> `unphosphorylated_form`

        Rate equation
        -------------
        v = V * [phosphorylated_form] / (K + [phosphorylated_form])

        Differential equation
        ---------------------
        d[unphosphorylated_form]/dt = + v
        d[phosphorylated_form]/dt = - v

        """
        description = self._preprocessing(sys._getframe().f_code.co_name, line_num, line, "V", "K")
        phosphorylated_form = description[0].strip(" ")
        if " --> " in description[1]:
            unphosphorylated_form = description[1].split(" --> ")[1].strip(" ")
        else:
            raise ValueError(
                f"line{line_num:d}: "
                "Use '-->' to specify the name of the dephosphorylated protein."
            )
        self._set_species(phosphorylated_form, unphosphorylated_form)
        self.protein_phosphorylation.append(Protein(unphosphorylated_form, phosphorylated_form))
        self.reactions.append(
            f"v[{line_num:d}] = "
            f"x[C.V{line_num:d}] * y[V.{phosphorylated_form}] / "
            f"(x[C.K{line_num:d}] + y[V.{phosphorylated_form}])"
        )
        counter_unphosphorylated_form, counter_phosphorylated_form = (0, 0)
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{unphosphorylated_form}]" in eq:
                counter_unphosphorylated_form += 1
                self.differential_equations[i] = eq + f" + v[{line_num:d}]"
            elif f"dydt[V.{phosphorylated_form}]" in eq:
                counter_phosphorylated_form += 1
                self.differential_equations[i] = eq + f" - v[{line_num:d}]"
        if counter_unphosphorylated_form == 0:
            self.differential_equations.append(
                f"dydt[V.{unphosphorylated_form}] = + v[{line_num:d}]"
            )
        if counter_phosphorylated_form == 0:
            self.differential_equations.append(
                f"dydt[V.{phosphorylated_form}] = - v[{line_num:d}]"
            )

    def phosphorylate(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `kinase`
            ↓
        `unphosphorylated_form` --> phosphorylated_form

        Example
        -------
        `kinase` phosphorylates `unphosphorylated_form` --> `phosphorylated_form`

        Rate equation
        -------------
        v = V * [kinase] * [unphosphorylated_form] / (K + [unphosphorylated_form])

        Differential equation
        ---------------------
        d[unphosphorylated_form]/dt = - v
        d[phosphorylated_form]/dt = + v

        """
        description = self._preprocessing(sys._getframe().f_code.co_name, line_num, line, "V", "K")
        kinase = description[0].strip(" ")
        if " --> " in description[1]:
            unphosphorylated_form = description[1].split(" --> ")[0].strip(" ")
            phosphorylated_form = description[1].split(" --> ")[1].strip(" ")
        else:
            raise ValueError(
                f"line{line_num:d}: "
                "Use '-->' to specify the name of the phosphorylated "
                "(or activated) protein."
            )
        if unphosphorylated_form == phosphorylated_form:
            raise ValueError(f"line{line_num:d}: {phosphorylated_form} <- Use a different name.")
        self._set_species(kinase, unphosphorylated_form, phosphorylated_form)
        self.protein_phosphorylation.append(Protein(unphosphorylated_form, phosphorylated_form))
        self.reactions.append(
            f"v[{line_num:d}] = "
            f"x[C.V{line_num:d}] * y[V.{kinase}] * y[V.{unphosphorylated_form}] / "
            f"(x[C.K{line_num:d}] + y[V.{unphosphorylated_form}])"
        )
        counter_unphosphorylated_form, counter_phosphorylated_form = (0, 0)
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{unphosphorylated_form}]" in eq:
                counter_unphosphorylated_form += 1
                self.differential_equations[i] = eq + f" - v[{line_num:d}]"
            elif f"dydt[V.{phosphorylated_form}]" in eq:
                counter_phosphorylated_form += 1
                self.differential_equations[i] = eq + f" + v[{line_num:d}]"
        if counter_unphosphorylated_form == 0:
            self.differential_equations.append(
                f"dydt[V.{unphosphorylated_form}] = - v[{line_num:d}]"
            )
        if counter_phosphorylated_form == 0:
            self.differential_equations.append(
                f"dydt[V.{phosphorylated_form}] = + v[{line_num:d}]"
            )

    def dephosphorylate(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `phosphatase`
            ↓
        `phosphorylated_form` --> `unphosphorylated_form`

        Example
        -------
        `phosphatase` dephosphorylates `phosphorylated_form` --> `unphosphorylated_form`

        Rate equation
        -------------
        v = V * [phosphatase] * [phosphorylated_form] / (K + [phosphorylated_form])

        Differential equation
        ---------------------
        d[unphosphorylated_form]/dt = + v
        d[phosphorylated_form]/dt = - v

        """
        description = self._preprocessing(sys._getframe().f_code.co_name, line_num, line, "V", "K")
        phosphatase = description[0].strip(" ")
        if " --> " in description[1]:
            phosphorylated_form = description[1].split(" --> ")[0].strip(" ")
            unphosphorylated_form = description[1].split(" --> ")[1].strip(" ")
        else:
            raise ValueError(
                f"line{line_num:d}: "
                "Use '-->' to specify the name of the dephosphorylated "
                "(or deactivated) protein."
            )
        if phosphorylated_form == unphosphorylated_form:
            raise ValueError(f"line{line_num:d}: {unphosphorylated_form} <- Use a different name.")
        self._set_species(phosphatase, phosphorylated_form, unphosphorylated_form)
        self.protein_phosphorylation.append(Protein(unphosphorylated_form, phosphorylated_form))
        self.reactions.append(
            f"v[{line_num:d}] = "
            f"x[C.V{line_num:d}] * y[V.{phosphatase}] * y[V.{phosphorylated_form}] / "
            f"(x[C.K{line_num:d}] + y[V.{phosphorylated_form}])"
        )
        counter_phosphorylated_form, counter_unphosphorylated_form = (0, 0)
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{phosphorylated_form}]" in eq:
                counter_phosphorylated_form += 1
                self.differential_equations[i] = eq + f" - v[{line_num:d}]"
            elif f"dydt[V.{unphosphorylated_form}]" in eq:
                counter_unphosphorylated_form += 1
                self.differential_equations[i] = eq + f" + v[{line_num:d}]"
        if counter_phosphorylated_form == 0:
            self.differential_equations.append(
                f"dydt[V.{phosphorylated_form}] = - v[{line_num:d}]"
            )
        if counter_unphosphorylated_form == 0:
            self.differential_equations.append(
                f"dydt[V.{unphosphorylated_form}] = + v[{line_num:d}]"
            )

    def transcribe(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `TF` --> `mRNA`

        Example
        -------
        - `TF` transcribes `mRNA`
        - `TF1` and `TF2` transcribe mRNA (AND-gate)
        - `TF` transcribes `mRNA`, repressed by `repressor` (Negative regulation)

        Rate equation
        -------------
        - v = V * [TF] ** n / (K ** n + [TF] ** n)
        - v = V * ([TF1] * [TF2]) ** n / (K ** n + ([TF1] * [TF2]) ** n)
        - v = V * [TF] ** n / (K ** n + [TF] ** n + ([repressor] / KF) ** nF)

        Differential equation
        ---------------------
        d[mRNA]/dt = + v

        """
        description = self._preprocessing(
            sys._getframe().f_code.co_name, line_num, line, "V", "K", "n", "KF", "nF"
        )
        repressor: Optional[str] = None
        ratio = self._word2scores(", repressed by", description[1])
        if not ratio or max(ratio) < 1.0:
            self.parameters.remove(f"KF{line_num:d}")
            self.parameters.remove(f"nF{line_num:d}")
            mRNA = description[1].strip()
            if " " in mRNA:
                # Fix typo in line{line_num:d}
                raise ValueError(
                    f"line{line_num:d}: "
                    "Add ', repressed by XXX' to describe negative regulation from XXX."
                )
        else:
            # Add negative regulation from `repressor`
            mRNA = description[1].split(", repressed by")[0].strip()
            repressor = description[1].split(", repressed by")[1].strip()
        if " and " not in description[0]:
            TF = description[0].strip(" ")
            self._set_species(mRNA, TF)
            if repressor is not None:
                self._set_species(repressor)
            self.reactions.append(
                f"v[{line_num:d}] = "
                f"x[C.V{line_num:d}] * y[V.{TF}] ** x[C.n{line_num:d}] / "
                f"(x[C.K{line_num:d}] ** x[C.n{line_num:d}] + "
                f"y[V.{TF}] ** x[C.n{line_num:d}]"
                + (
                    ")"
                    if repressor is None
                    else f" + (y[V.{repressor}] / x[C.KF{line_num:d}]) ** x[C.nF{line_num:d}])"
                )
            )
        else:
            # AND-gate
            TF1 = description[0].split(" and ")[0].strip(" ")
            TF2 = description[0].split(" and ")[1].strip(" ")
            self._set_species(mRNA, TF1, TF2)
            if repressor is not None:
                self._set_species(repressor)
            self.reactions.append(
                f"v[{line_num:d}] = "
                f"x[C.V{line_num:d}] * (y[V.{TF1}]*y[V.{TF2}]) ** x[C.n{line_num:d}] / "
                f"(x[C.K{line_num:d}] ** x[C.n{line_num:d}] + "
                f"(y[V.{TF1}]*y[V.{TF2}]) ** x[C.n{line_num:d}]"
                + (
                    ")"
                    if repressor is None
                    else f" + (y[V.{repressor}] / x[C.KF{line_num:d}]) ** x[C.nF{line_num:d}])"
                )
            )
        counter_mRNA = 0
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{mRNA}]" in eq:
                counter_mRNA += 1
                self.differential_equations[i] = eq + f" + v[{line_num:d}]"
        if counter_mRNA == 0:
            self.differential_equations.append(f"dydt[V.{mRNA}] = + v[{line_num:d}]")

    def is_translated(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `mRNA` --> `protein`

        Example
        -------
        `mRNA` is translated into `protein`

        Rate equation
        -------------
        v = kf * [mRNA]

        Differential equation
        ---------------------
        d[protein]/dt = + v

        """
        description = self._preprocessing(sys._getframe().f_code.co_name, line_num, line, "kf")
        mRNA = description[0].strip(" ")
        protein = description[1].strip(" ")
        self._set_species(mRNA, protein)
        self.reactions.append(f"v[{line_num:d}] = x[C.kf{line_num:d}] * y[V.{mRNA}]")
        counter_protein = 0
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{protein}]" in eq:
                counter_protein += 1
                self.differential_equations[i] = eq + f" + v[{line_num:d}]"
        if counter_protein == 0:
            self.differential_equations.append(f"dydt[V.{protein}] = + v[{line_num:d}]")

    def synthesize(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `catalyst`
            ↓
        0 --> `product`

        Example
        -------
        `catalyst` synthesizes `product`.

        Rate equation
        -------------
        v = kf * [catalyst]

        Differential equation
        ---------------------
        d[product]/dt = + v

        """
        description = self._preprocessing(sys._getframe().f_code.co_name, line_num, line, "kf")
        catalyst = description[0].strip(" ")
        product = description[1].strip(" ")
        self._set_species(catalyst, product)
        self.reactions.append(f"v[{line_num:d}] = x[C.kf{line_num:d}] * y[V.{catalyst}]")
        counter_product = 0
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{product}]" in eq:
                counter_product += 1
                self.differential_equations[i] = eq + f" + v[{line_num:d}]"
        if counter_product == 0:
            self.differential_equations.append(f"dydt[V.{product}] = + v[{line_num:d}]")

    def is_synthesized(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        0 --> `chemical_species`

        Example
        -------
        `chemical_species` is synthesized.

        Rate equation
        -------------
        v = kf

        Differential equation
        ---------------------
        d[chemical_species]/dt = + v

        """
        description = self._preprocessing(sys._getframe().f_code.co_name, line_num, line, "kf")
        chemical_species = description[0].strip(" ")
        self._set_species(chemical_species)
        self.reactions.append(f"v[{line_num:d}] = x[C.kf{line_num:d}]")
        counter_chemical_species = 0
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{chemical_species}]" in eq:
                counter_chemical_species += 1
                self.differential_equations[i] = eq + f" + v[{line_num:d}]"
        if counter_chemical_species == 0:
            self.differential_equations.append(f"dydt[V.{chemical_species}] = + v[{line_num:d}]")

    def degrade(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `protease`
            ↓
        `protein` --> 0

        Example
        -------
        `protease` degrades `protein`.

        Rate equation
        -------------
        v = kf * [protease]

        Differential equation
        ---------------------
        d[protein]/dt = - v

        """
        description = self._preprocessing(sys._getframe().f_code.co_name, line_num, line, "kf")
        protease = description[0].strip(" ")
        protein = description[1].strip(" ")
        self._set_species(protease, protein)
        self.reactions.append(f"v[{line_num:d}] = x[C.kf{line_num:d}] * y[V.{protease}]")
        counter_protein = 0
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{protein}]" in eq:
                counter_protein += 1
                self.differential_equations[i] = eq + f" - v[{line_num:d}]"
        if counter_protein == 0:
            self.differential_equations.append(f"dydt[V.{protein}] = - v[{line_num:d}]")

    def is_degraded(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `chemical_species` --> 0

        Example
        -------
        `chemical_species` is degraded.

        Rate equation
        -------------
        v = kf * [chemical_species]

        Differential equation
        ---------------------
        d[chemical_species]/dt = - v

        """
        description = self._preprocessing(sys._getframe().f_code.co_name, line_num, line, "kf")
        chemical_species = description[0].strip(" ")
        self._set_species(chemical_species)
        self.reactions.append(f"v[{line_num:d}] = x[C.kf{line_num:d}] * y[V.{chemical_species}]")
        counter_chemical_species = 0
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{chemical_species}]" in eq:
                counter_chemical_species += 1
                self.differential_equations[i] = eq + f" - v[{line_num:d}]"
        if counter_chemical_species == 0:
            self.differential_equations.append(f"dydt[V.{chemical_species}] = - v[{line_num:d}]")

    def is_translocated(self, line_num: int, line: str) -> None:
        """
        Event
        -----
        `pre_translocation` <=> `post_translocation`
        (Volume_pre_translocation <-> Volume_post_translocation)

        Example
        -------
        `pre_translocation` is translocated from one location to another \
        (pre_volume, post_volume) --> post_translocation.

        Rate equation
        -------------
        v = kf * [pre_translocation] - kr * (post_volume / pre_volume) \
            * [post_translocation]

        Differential equation
        ---------------------
        d[pre_translocation]/dt = - v
        d[post_translocation]/dt = + v * (pre_volume / post_volume)

        """
        description = self._preprocessing(
            sys._getframe().f_code.co_name, line_num, line, "kf", "kr"
        )
        pre_translocation = description[0].strip(" ")
        if " --> " in description[1]:
            post_translocation = description[1].split(" --> ")[1].strip(" ")
        else:
            raise ValueError(
                f"line{line_num:d}: "
                "Use '-->' to specify the name of the species after translocation."
            )
        if pre_translocation == post_translocation:
            raise ValueError(f"line{line_num:d}: {post_translocation} <- Use a different name.")
        # Information about compartment volumes
        if "(" in description[1] and ")" in description[1]:
            [pre_volume, post_volume] = description[1].split("(")[-1].split(")")[0].split(",")
            if not self._isfloat(pre_volume.strip(" ")) or not self._isfloat(
                post_volume.strip(" ")
            ):
                raise ValueError("pre_volume and post_volume must be float or int.")
        else:
            [pre_volume, post_volume] = ["1", "1"]
        self._set_species(pre_translocation, post_translocation)
        self.reactions.append(
            f"v[{line_num:d}] = x[C.kf{line_num:d}] * y[V.{pre_translocation}] - "
            f"x[C.kr{line_num:d}] * y[V.{post_translocation}]"
        )
        if float(pre_volume.strip(" ")) != float(post_volume.strip(" ")):
            self.reactions[-1] = (
                f"v[{line_num:d}] = "
                f"x[C.kf{line_num:d}] * y[V.{pre_translocation}] - "
                f"x[C.kr{line_num:d}] * "
                f"({post_volume.strip()} / {pre_volume.strip()}) * "
                f"y[V.{post_translocation}]"
            )
        counter_pre_translocation, counter_post_translocation = (0, 0)
        for i, eq in enumerate(self.differential_equations):
            if f"dydt[V.{pre_translocation}]" in eq:
                counter_pre_translocation += 1
                self.differential_equations[i] = eq + f" - v[{line_num:d}]"
            elif f"dydt[V.{post_translocation}]" in eq:
                counter_post_translocation += 1
                self.differential_equations[i] = eq + f" + v[{line_num:d}]"
                if float(pre_volume.strip(" ")) != float(post_volume.strip(" ")):
                    self.differential_equations[
                        i
                    ] += f" * ({pre_volume.strip()} / {post_volume.strip()})"
        if counter_pre_translocation == 0:
            self.differential_equations.append(f"dydt[V.{pre_translocation}] = - v[{line_num:d}]")
        if counter_post_translocation == 0:
            self.differential_equations.append(f"dydt[V.{post_translocation}] = + v[{line_num:d}]")
            if float(pre_volume.strip(" ")) != float(post_volume.strip(" ")):
                self.differential_equations[
                    -1
                ] += f" * ({pre_volume.strip()} / {post_volume.strip()})"

    def create_ode(self) -> None:
        """
        Find a keyword in each line to identify the reaction rule and
        construct an ODE model.

        """
        with open(self.input_txt, encoding="utf-8") as f:
            lines = f.readlines()
        for line_num, line in enumerate(lines, start=1):
            # Remove double spaces
            while True:
                if "  " not in line:
                    break
                else:
                    line = line.replace("  ", " ")
            # Comment out
            line = line.split("#")[0].rstrip(" ")
            if not line.strip():
                # Skip blank lines
                continue
            elif lines.count(line) > 1:
                # Find duplicate lines
                raise ValueError(
                    f"Reaction '{line}' is duplicated in lines "
                    + ", ".join([str(i + 1) for i, rxn in enumerate(lines) if rxn == line])
                )
            # About observables
            elif line.startswith("@obs "):
                line = line.lstrip("@obs ")
                self.obs_desc.append(line.split("="))
            # About simulation info.
            elif line.startswith("@sim "):
                line = line.lstrip("@sim ")
                if line.count(":") != 1:
                    raise SyntaxError("Missing colon")
                else:
                    if line.startswith("tspan"):
                        t_info = line.split(":")[-1].strip()
                        if "[" in t_info and "]" in t_info:
                            [t0, tf] = t_info.split("[")[-1].split("]")[0].split(",")
                            if t0.strip(" ").isdecimal() and tf.strip(" ").isdecimal():
                                self.sim_tspan.append(t0)
                                self.sim_tspan.append(tf)
                            else:
                                raise TypeError("@sim tspan: [t0, tf] must be a list of integers.")
                        else:
                            raise ValueError(
                                "tspan must be a two element vector [t0, tf] "
                                "specifying the initial and final times."
                            )
                    elif line.startswith("unperturbed"):
                        self.sim_unperturbed += line.split(":")[-1].strip()
                    elif line.startswith("condition "):
                        self.sim_conditions.append(line.lstrip("condition ").split(":"))
                    else:
                        raise ValueError(
                            "Available options are: "
                            "'@sim tspan:', '@sim unperturbed:' or '@sim condition XXX:'."
                        )
            # Detect reaction rule
            else:
                for reaction_rule, words in self.rule_words.items():
                    if any([self._remove_prepositions(word) in line for word in words]):
                        exec("self." + reaction_rule + "(line_num, line)")
                        break
                else:
                    unregistered_rule = self._get_partial_similarity(line)
                    raise ValueError(
                        f"Unregistered words in line{line_num:d}: {line}"
                        + (
                            f"\nMaybe: '{unregistered_rule.expected}'."
                            if unregistered_rule.expected is not None
                            else ""
                        )
                    )

    def check_species_names(self) -> None:
        """
        Check whether user-defined names of model species are appropriate.
        """
        unique_pairs = set(self.protein_phosphorylation)
        for one in self.protein_phosphorylation:
            if self.protein_phosphorylation.count(one) % 2 == 1:
                for another in unique_pairs:
                    if (
                        one.unphosphorylated == another.unphosphorylated
                        and one.phosphorylated != another.phosphorylated
                    ) or (
                        one.unphosphorylated != another.unphosphorylated
                        and one.phosphorylated == another.phosphorylated
                    ):
                        raise NameError(
                            "These species names should be same: "
                            + (
                                f"'{one.unphosphorylated}' and '{another.unphosphorylated}'."
                                if one.unphosphorylated != another.unphosphorylated
                                else f"'{one.phosphorylated}' and '{another.phosphorylated}'."
                            )
                        )
