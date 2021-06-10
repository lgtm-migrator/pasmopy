import os
import re
import shutil
from dataclasses import dataclass, field
from typing import List

from . import julia_template as jl
from .reaction_rules import ReactionRules


@dataclass
class Text2Model(ReactionRules):
    """Build a BioMASS-formatted model based on template.

    Attributes
    ----------
    input_txt : str
        Model description file (*.txt), e.g., 'Kholodenko_JBC_1999.txt'

    lang : str (default: 'python')
        Either 'python' or 'julia'.

        - 'python': biomass (https://github.com/biomass-dev/biomass)
        - 'julia': BioMASS.jl (https://github.com/biomass-dev/BioMASS.jl)
    """

    input_txt: str
    lang: str = "python"
    indentation: str = field(default=4 * " ", init=False)

    def __post_init__(self) -> None:
        if not os.path.isfile(self.input_txt):
            raise FileNotFoundError(f"{self.input_txt} does not exist.")
        if self.lang not in ["python", "julia"]:
            raise ValueError("lang must be either 'python' or 'julia'.")
        self.name: str = os.path.splitext(self.input_txt)[0]

    def _update_parameters(self) -> None:
        """
        Update name2idx/parameters.py
        """
        if self.lang == "python":
            with open(
                os.path.join(
                    os.path.dirname(__file__),
                    "template",
                    "name2idx",
                    "parameters.py",
                ),
                encoding="utf-8",
                mode="r",
            ) as f:
                lines = f.readlines()
            for line_num, line in enumerate(lines):
                if line.startswith("NAMES: List[str] = []"):
                    lines[line_num] = "NAMES: List[str] = [\n"
                    lines[line_num] += (
                        f"{self.indentation}'"
                        + f"',\n{self.indentation}'".join(self.parameters)
                        + "',\n"
                    )
                    lines[line_num] += "]\n"
            with open(
                os.path.join(
                    f"{self.name}",
                    "name2idx",
                    "parameters.py",
                ),
                encoding="utf-8",
                mode="w",
            ) as f:
                f.writelines(lines)
        else:
            lines = jl.PARAMETERS.splitlines()
            for line_num, line in enumerate(lines):
                if line.startswith("const NAMES = []"):
                    lines[line_num] = "const NAMES = [\n"
                    lines[line_num] += (
                        f'{self.indentation}"'
                        + f'",\n{self.indentation}"'.join(self.parameters)
                        + '",\n'
                    )
                    lines[line_num] += "]\n"
            with open(
                os.path.join(
                    f"{self.name}_jl",
                    "name2idx",
                    "parameters.jl",
                ),
                encoding="utf-8",
                mode="w",
            ) as f:
                f.write("\n".join(lines))

    def _update_species(self) -> None:
        """
        Update name2idx/species.py
        """
        if self.lang == "python":
            with open(
                os.path.join(
                    os.path.dirname(__file__),
                    "template",
                    "name2idx",
                    "species.py",
                ),
                encoding="utf-8",
                mode="r",
            ) as f:
                lines = f.readlines()
            for line_num, line in enumerate(lines):
                if line.startswith("NAMES: List[str] = []"):
                    lines[line_num] = "NAMES: List[str] = [\n"
                    lines[line_num] += (
                        "{}'".format(self.indentation)
                        + "',\n{}'".format(self.indentation).join(self.species)
                        + "',\n"
                    )
                    lines[line_num] += "]\n"
            with open(
                os.path.join(
                    f"{self.name}",
                    "name2idx",
                    "species.py",
                ),
                encoding="utf-8",
                mode="w",
            ) as f:
                f.writelines(lines)
        else:
            lines = jl.SPECIES.splitlines()
            for line_num, line in enumerate(lines):
                if line.startswith("const NAMES = []"):
                    lines[line_num] = "const NAMES = [\n"
                    lines[line_num] += (
                        '{}"'.format(self.indentation)
                        + '",\n{}"'.format(self.indentation).join(self.species)
                        + '",\n'
                    )
                    lines[line_num] += "]\n"
            with open(
                os.path.join(
                    f"{self.name}_jl",
                    "name2idx",
                    "species.jl",
                ),
                encoding="utf-8",
                mode="w",
            ) as f:
                f.write("\n".join(lines))

    def _update_set_model(self) -> None:
        """Update set_model.py

        If you don't write info., all parameter values and initial values are
        initialized to 1.0 and 0.0, respectively.
        """
        if self.lang == "python":
            with open(
                os.path.join(os.path.dirname(__file__), "template", "set_model.py"),
                encoding="utf-8",
                mode="r",
            ) as f:
                lines = f.readlines()
            for line_num, line in enumerate(lines):
                if line.startswith(2 * self.indentation + "v = {}\n"):
                    # Write flux vector: v
                    lines[line_num + 1] = (
                        2 * self.indentation
                        + f"\n{2 * self.indentation}".join(self.reactions)
                        + "\n\n"
                    )
                elif line.startswith(2 * self.indentation + "dydt = [0] * V.NUM\n"):
                    # Write right-hand side of the differential equation: dydt
                    lines[line_num + 1] = (
                        2 * self.indentation
                        + f"\n{2 * self.indentation}".join(self.differential_equations)
                        + "\n\n"
                    )
                elif line.startswith(self.indentation + "return x"):
                    if not self.param_info:
                        # Set all parameter values = 1.0 if param_info is not given
                        lines[line_num - 1] = (
                            f"{self.indentation + 'x[C.'}"
                            + f"] = 1.0\n{self.indentation + 'x[C.'}".join(self.parameters)
                            + "] = 1.0\n\n"
                        )
                    else:
                        # Set parameter values using param_info
                        lines[line_num - 1] = (
                            "{}".format(self.indentation)
                            + "\n{}".format(self.indentation).join(self.param_info)
                            + "\n\n"
                        )
                elif line.startswith(self.indentation + "return y0"):
                    if self.init_info:
                        # Set initial values using init_info
                        lines[line_num - 1] = (
                            "{}".format(self.indentation)
                            + "\n{}".format(self.indentation).join(self.init_info)
                            + "\n\n"
                        )
            with open(
                os.path.join(
                    f"{self.name}",
                    "set_model.py",
                ),
                encoding="utf-8",
                mode="w",
            ) as f:
                f.writelines(lines)
        else:
            lines = jl.SET_MODEL.splitlines()
            for line_num, line in enumerate(lines):
                if line.startswith(self.indentation + "v = Dict{Int64,Float64}()"):
                    # Write flux vector: v
                    lines[line_num + 1] = (
                        self.indentation + f"\n{self.indentation}".join(self.reactions) + "\n"
                    )
                    lines[line_num + 1] = (
                        lines[line_num + 1]
                        .replace("x[C.", "p[C.")
                        .replace("y[V.", "u[V.")
                        .replace("**", "^")
                    )
                    # Write right-hand side of the differential equation: dydt
                    lines[line_num + 5] = (
                        self.indentation
                        + f"\n{self.indentation}".join(self.differential_equations)
                        + "\n"
                    ).replace("dydt[V.", "du[V.")
                elif line.startswith(self.indentation + "return p"):
                    if not self.param_info:
                        # Set all parameter values = 1.0 if param_info is not given
                        lines[line_num - 1] = (
                            f"{self.indentation + 'p[C.'}"
                            + f"] = 1.0\n{self.indentation + 'p[C.'}".join(self.parameters)
                            + "] = 1.0\n\n"
                        )
                    else:
                        # Set parameter values using param_info
                        lines[line_num - 1] = (
                            "{}".format(self.indentation)
                            + "\n{}".format(self.indentation).join(self.param_info)
                            + "\n\n"
                        ).replace("x[C.", "p[C.")
                elif line.startswith(self.indentation + "return u0"):
                    if self.init_info:
                        # Set initial values using init_info
                        lines[line_num - 1] = (
                            "{}".format(self.indentation)
                            + "\n{}".format(self.indentation).join(self.init_info)
                            + "\n\n"
                        ).replace("y0[V.", "u0[V.")
            with open(
                os.path.join(
                    f"{self.name}_jl",
                    "set_model.jl",
                ),
                encoding="utf-8",
                mode="w",
            ) as f:
                f.write("\n".join(lines))

    def _update_set_search_param(self) -> None:
        """
        Update set_search_param.py
        """
        if self.lang == "python":
            with open(
                os.path.join(os.path.dirname(__file__), "template", "set_search_param.py"),
                encoding="utf-8",
                mode="r",
            ) as f:
                lines = f.readlines()
            for line_num, line in enumerate(lines):
                if "idx_params = []" in line:
                    # Write all parameters in idx_params (except for param_excluded)
                    lines[line_num] = f"{self.indentation}idx_params = [\n"
                    lines[line_num] += (
                        "{}".format(2 * self.indentation + "C.")
                        + ",\n{}".format(2 * self.indentation + "C.").join(self.parameters)
                        + ",\n"
                    )
                    lines[line_num] += f"{self.indentation}]\n"
                    for param_name in self.param_excluded:
                        # Comment out parameters in param_excluded
                        lines[line_num] = lines[line_num].replace(
                            f"C.{param_name},", f"# C.{param_name},"
                        )
                elif "# parameter constraints" in line:
                    # Add parameter constraints
                    lines[line_num + 1] = (
                        "{}".format(2 * self.indentation)
                        + "\n{}".format(2 * self.indentation).join(self.param_constraints)
                        + "\n\n"
                    )
            with open(
                os.path.join(f"{self.name}", "set_search_param.py"),
                encoding="utf-8",
                mode="w",
            ) as f:
                f.writelines(lines)
        else:
            lines = jl.SET_SEARCH_PARAM.splitlines()
            for line_num, line in enumerate(lines):
                if "search_idx_params::Vector{Int} = []" in line:
                    # Write all parameters in idx_params (except for param_excluded)
                    lines[line_num] = (
                        f"{self.indentation}search_idx_params" + "::Vector{Int} = [\n"
                    )
                    lines[line_num] += (
                        "{}".format(2 * self.indentation + "C.")
                        + ",\n{}".format(2 * self.indentation + "C.").join(self.parameters)
                        + ",\n"
                    )
                    lines[line_num] += f"{self.indentation}]\n"
                    for param_name in self.param_excluded:
                        # Comment out parameters in param_excluded
                        lines[line_num] = lines[line_num].replace(
                            f"C.{param_name},", f"# C.{param_name},"
                        )
                elif "# parameter constraints" in line:
                    # Add parameter constraints
                    lines[line_num + 1] = (
                        "{}".format(self.indentation)
                        + "\n{}".format(self.indentation).join(self.param_constraints)
                        + "\n"
                    ).replace("x[C.", "p[C.")
            with open(
                os.path.join(f"{self.name}_jl", "set_search_param.jl"),
                encoding="utf-8",
                mode="w",
            ) as f:
                f.write("\n".join(lines))

    def _convert_names(
        self,
        line: str,
        p: List[str] = [],
        u: List[str] = [],
        init: List[str] = [],
    ) -> str:
        """
        Replace
        - p[xxx] with x[C.xxx]
        - u[xxx] with Y[:, V.xxx]
        - init[xxx] with y0[V.xxx]

        Parameters
        ----------
        p : list of strings (default: [])
            Parameters.

        u : list of strings (default: [])
            Species.

        init : list of strings (default: [])
            Initial conditions.

        Returns
        -------
        line : string
            Each line.

        """
        for p_name in p:
            if not p_name.strip() in self.parameters:
                raise NameError(f"{p_name.strip()} is not defined in model parameters.")
            else:
                line = (
                    line.replace(f"p[{p_name.strip()}]", f"x[C.{p_name.strip()}]")
                    if self.lang == "python"
                    else line.replace(f"p[{p_name.strip()}]", f"p[C.{p_name.strip()}]")
                )
        for s_name in u:
            if not s_name.strip() in self.species:
                raise NameError(f"{s_name.strip()} is not defined in model species.")
            else:
                line = (
                    line.replace(f"u[{s_name.strip()}]", f"sol.y[V.{s_name.strip()}, :]")
                    if self.lang == "python"
                    else line.replace(f"u[{s_name.strip()}]", f"sol.u[j][V.{s_name.strip()}]")
                )
        for s_name in init:
            if not s_name.strip() in self.species:
                raise NameError(f"{s_name.strip()} is not defined in model species.")
            else:
                line = (
                    line.replace(f"init[{s_name.strip()}]", f"y0[V.{s_name.strip()}]")
                    if self.lang == "python"
                    else line.replace(f"init[{s_name.strip()}]", f"u0[V.{s_name.strip()}]")
                )
        return line

    def _update_observable(self) -> None:
        """
        Update observable.py
        """
        if self.lang == "python":
            with open(
                os.path.join(os.path.dirname(__file__), "template", "observable.py"),
                encoding="utf-8",
                mode="r",
            ) as f:
                lines = f.readlines()
            if not self.sim_conditions:
                # When sim condition is not given, add 'sim condition control: pass'
                self.sim_conditions = [["control", "pass"]]
            for line_num, line in enumerate(lines):
                if line.startswith("observables = []"):
                    # Write observables
                    lines[line_num] = "observables = [\n"
                    lines[line_num + 1] = (
                        f"{self.indentation}'"
                        + f"',\n{self.indentation}'".join(
                            [desc[0].strip() for desc in self.obs_desc]
                        )
                        + "',\n"
                    )
                    lines[line_num + 1] += "]\n"
                elif "t = range(101)" in line:
                    # Write interval of integration
                    if self.sim_tspan:
                        lines[line_num] = "{}t = range({}, {}+1)".format(
                            self.indentation,
                            self.sim_tspan[0].strip(),
                            self.sim_tspan[1].strip(),
                        )
                elif line.startswith(f"{self.indentation}conditions = []"):
                    # Write sim.condition
                    lines[line_num] = f"{self.indentation}conditions = [\n"
                    lines[line_num + 1] = (
                        f"{2 * self.indentation}'"
                        + f"',\n{2 * self.indentation}'".join(
                            [condition[0].strip() for condition in self.sim_conditions]
                        )
                        + "',\n"
                    )
                    lines[line_num + 1] += f"{self.indentation}]\n"
                elif "# unperturbed steady state" in line:
                    if self.sim_unperturbed:
                        lines[line_num + 1] = (
                            2 * self.indentation
                            + f"\n{2 * self.indentation}".join(
                                c.strip() for c in self.sim_unperturbed.split(sep=";")
                            )
                            + "\n"
                        )
                        lines[line_num + 1] += (
                            2 * self.indentation
                            + "y0 = self._get_steady_state(self.diffeq, y0, tuple(x))\n"
                            + 2 * self.indentation
                            + f"if not y0:\n{3 * self.indentation}return False\n"
                        )
                        # pa: parameters
                        # init: initial conditions
                        lines[line_num + 1] = self._convert_names(
                            line=lines[line_num + 1],
                            p=re.findall(r"p\[(.*?)\]", self.sim_unperturbed),
                            init=re.findall(r"init\[(.*?)\]", self.sim_unperturbed),
                        )
                elif "for i, condition in enumerate(self.conditions):" in line:
                    for i, condition in enumerate(self.sim_conditions):
                        # Use ';' for adding description of each condition
                        if i == 0:
                            lines[line_num + 1] = (
                                3 * self.indentation
                                + f'if condition == \'{condition[0].strip(" ")}\':\n'
                                + 4 * self.indentation
                                + f"\n{4 * self.indentation}".join(
                                    c.strip(" ") for c in condition[1].split(sep=";")
                                )
                                + ("\n\n" if len(self.sim_conditions) == 1 else "")
                            )
                        else:
                            lines[line_num + 1] += (
                                3 * self.indentation
                                + f'elif condition == \'{condition[0].strip(" ")}\':\n'
                                + 4 * self.indentation
                                + f"\n{4 * self.indentation}".join(
                                    c.strip(" ") for c in condition[1].split(sep=";")
                                )
                                + "\n\n"
                            )
                        # pa: parameters
                        # init: initial conditions
                        lines[line_num + 1] = self._convert_names(
                            line=lines[line_num + 1],
                            p=re.findall(r"p\[(.*?)\]", condition[1]),
                            init=re.findall(r"init\[(.*?)\]", condition[1]),
                        )
                elif "sol is None:" in line:
                    lines[line_num + 3] = ""  # initialization (default: pass)
                    for desc in self.obs_desc:
                        lines[line_num + 3] += (
                            "{}".format(4 * self.indentation)
                            + "self.simulations"
                            + f"[observables.index('{desc[0].strip()}'), :, i] = (\n"
                            + f"{5 * self.indentation}"
                            + desc[1].strip(" ").strip()
                        )
                        # p: parameters
                        # u: species
                        lines[line_num + 3] = self._convert_names(
                            line=lines[line_num + 3],
                            p=re.findall(r"p\[(.*?)\]", desc[1]),
                            u=re.findall(r"u\[(.*?)\]", desc[1]),
                        )
                        lines[line_num + 3] += "\n{}".format(4 * self.indentation + ")\n")
            with open(
                os.path.join(f"{self.name}", "observable.py"),
                encoding="utf-8",
                mode="w",
            ) as f:
                f.writelines(lines)
        else:
            self._split_observables_julia()

    def _split_observables_julia(self) -> None:
        """
        Create observable.jl, simulation.jl and experimental_data.jl
        """
        # observable.jl
        lines = jl.OBSERVABLE.splitlines()
        for line_num, line in enumerate(lines):
            if "const observables = []" in line:
                lines[line_num] = "const observables = [\n"
                lines[line_num + 1] = (
                    f'{self.indentation}"'
                    + f'",\n{self.indentation}"'.join([desc[0].strip() for desc in self.obs_desc])
                    + '",\n'
                )
                lines[line_num + 1] += "]\n"
        with open(
            os.path.join(f"{self.name}_jl", "observable.jl"),
            encoding="utf-8",
            mode="w",
        ) as f:
            f.write("\n".join(lines))
        # simulation.jl
        lines = jl.SIMULATION.splitlines()
        for line_num, line in enumerate(lines):
            if line.startswith("const t = collect(0.0:dt:100.0)"):
                # Write interval of integration
                if self.sim_tspan:
                    lines[line_num] = "const t = collect({}:dt:{})".format(
                        self.sim_tspan[0].strip(),
                        self.sim_tspan[1].strip(),
                    )
            elif line.startswith("const conditions = []"):
                # Write sim.condition
                lines[line_num] = "const conditions = ["
                lines[line_num + 1] = (
                    f'{self.indentation}"'
                    + f'",\n{self.indentation}"'.join(
                        [condition[0].strip() for condition in self.sim_conditions]
                    )
                    + '",\n'
                )
                lines[line_num + 1] += "]\n"
            elif "# unperturbed steady state" in line:
                if self.sim_unperturbed:
                    lines[line_num + 1] = (
                        self.indentation
                        + f"\n{self.indentation}".join(
                            c.strip() for c in self.sim_unperturbed.split(sep=";")
                        )
                        + "\n"
                    )
                    lines[line_num + 1] += (
                        f"{self.indentation}u0 = get_steady_state(diffeq!, u0, p)\n"
                        + f"{self.indentation}if isempty(u0)\n"
                        + f"{2 * self.indentation}return false\n"
                        + f"{self.indentation}end\n"
                    )
                    # p: parameters
                    # init: initial conditions
                    lines[line_num + 1] = self._convert_names(
                        line=lines[line_num + 1],
                        p=re.findall(r"p\[(.*?)\]", self.sim_unperturbed),
                        init=re.findall(r"init\[(.*?)\]", self.sim_unperturbed),
                    )
            elif "for (i, condition) in enumerate(conditions)" in line:
                for i, condition in enumerate(self.sim_conditions):
                    # Use ';' for adding description of each condition
                    if i == 0:
                        lines[line_num + 1] = (
                            3 * self.indentation
                            + f'if condition == "{condition[0].strip(" ")}"\n'
                            + 4 * self.indentation
                            + f"\n{4 * self.indentation}".join(
                                c.strip(" ") for c in condition[1].split(sep=";")
                            )
                            + ("\n\n" if len(self.sim_conditions) == 1 else "")
                        )
                    else:
                        lines[line_num + 1] += (
                            3 * self.indentation
                            + f'elseif condition == "{condition[0].strip(" ")}"\n'
                            + 4 * self.indentation
                            + f"\n{4 * self.indentation}".join(
                                c.strip(" ") for c in condition[1].split(sep=";")
                            )
                            + f"\n{3 * self.indentation}end\n"
                        )
                    # p: parameters
                    # init: initial conditions
                    lines[line_num + 1] = self._convert_names(
                        line=lines[line_num + 1],
                        p=re.findall(r"p\[(.*?)\]", condition[1]),
                        init=re.findall(r"init\[(.*?)\]", condition[1]),
                    )
            elif "if sol === nothing" in line:
                lines[line_num + 4] = ""  # initialization (default: # line_num + 4)
                for desc in self.obs_desc:
                    lines[line_num + 4] += (
                        "{}".format(4 * self.indentation)
                        + "simulations"
                        + f'[observables_index("{desc[0].strip()}"), j, i] = (\n'
                        + f"{5 * self.indentation}"
                        + desc[1].strip(" ").strip()
                    )
                    # p: parameters
                    # u: species
                    lines[line_num + 4] = self._convert_names(
                        line=lines[line_num + 4],
                        p=re.findall(r"p\[(.*?)\]", desc[1]),
                        u=re.findall(r"u\[(.*?)\]", desc[1]),
                    )
                    lines[line_num + 4] += "\n{}".format(4 * self.indentation + ")\n")
        with open(
            os.path.join(f"{self.name}_jl", "simulation.jl"),
            encoding="utf-8",
            mode="w",
        ) as f:
            f.write("\n".join(lines))
        # experimental_data.jl
        lines = jl.EXPERIMENTAL_DATA.splitlines()
        with open(
            os.path.join(f"{self.name}_jl", "experimental_data.jl"),
            encoding="utf-8",
            mode="w",
        ) as f:
            f.write("\n".join(lines))

    def convert(self, overwrite: bool = False) -> None:
        """
        Convert text to a biomass-formatted model.

        Parameters
        ----------
        overwrite : bool (defauld: False)
            If True, the model folder will be overwritten.

        Examples
        --------
        >>> from pasmopy import Text2Model
        >>> Text2Model("Kholodenko_JBC_1999.txt").convert()

        """
        if overwrite and os.path.isdir(
            f"{self.name}" if self.lang == "python" else f"{self.name}_jl"
        ):
            shutil.rmtree(f"{self.name}" if self.lang == "python" else f"{self.name}_jl")
        if self.lang == "python":
            shutil.copytree(
                os.path.join(
                    os.path.dirname(__file__),
                    "template",
                ),
                f"{self.name}",
            )
        else:
            os.makedirs(os.path.join(f"{self.name}_jl", "name2idx"))

        self.create_ode()
        self.check_species_names()
        self._update_parameters()
        self._update_species()
        self._update_set_model()
        self._update_set_search_param()
        self._update_observable()
        if self.lang == "julia":
            # Create fitness.jl
            lines = jl.FITNESS.splitlines()
            with open(
                os.path.join(f"{self.name}_jl", "fitness.jl"),
                encoding="utf-8",
                mode="w",
            ) as f:
                f.write("\n".join(lines))
        print(
            "Model Information\n"
            "-----------------\n"
            f"{len(self.reactions):d} reactions\n"
            f"{len(self.species):d} species\n"
            f"{len(self.parameters):d} parameters"
        )

    def to_markdown(self, n_reaction: int) -> None:
        """
        Create markdown table describing differential equations.

        Parameters
        ----------
        n_reaction : int
            The number of rate equations in the model.

        Examples
        --------
        >>> from pasmopy import Text2Model
        >>> Text2Model("Kholodenko_JBC_1999.txt").to_markdown(25)

        """
        os.makedirs(os.path.join("markdown", f"{self.name.split(os.sep)[-1]}"), exist_ok=True)
        self.create_ode()
        self.check_species_names()
        with open(self.input_txt, encoding="utf-8") as f:
            lines = f.readlines()
        for num, line in enumerate(lines):
            if n_reaction <= num:
                break
            else:
                rate_equation_formatted = f"{self.reactions[num]}".split("=")[1].strip()
                for p_names in self.parameters:
                    if f" ** x[C.{p_names.strip()}]" in f"{self.reactions[num]}":
                        # Hill coefficients
                        rate_equation_formatted = rate_equation_formatted.replace(
                            f" ** x[C.{p_names.strip()}]",
                            f"<sup>{p_names.strip()}</sup>".replace(
                                f"{num + 1:d}", f"<sub>{num + 1:d}</sub>"
                            ),
                        )
                    elif f"x[C.{p_names.strip()}]" in f"{self.reactions[num]}":
                        # Others
                        rate_equation_formatted = rate_equation_formatted.replace(
                            f"x[C.{p_names.strip()}]",
                            f"{p_names.strip()}".replace(
                                f"{num + 1:d}", f"<sub>{num + 1:d}</sub>"
                            ),
                        )
                lines[num] = (
                    f"|{num + 1:d}|"
                    + line.split("|")[0].rstrip()
                    + f"|{rate_equation_formatted.replace('*', '·').replace('y[V.', '[')}|"
                    + "\n"
                )
        with open(
            os.path.join("markdown", f"{self.name.split(os.sep)[-1]}", "rate_equation.md"),
            encoding="utf-8",
            mode="w",
        ) as f:
            f.writelines(
                [
                    "|No.|Reactions|Rate equations|\n|---|---------|--------------|\n",
                    *lines[:n_reaction],
                ]
            )
        # Differential equation
        differential_equations_formatted = [
            eq.replace("*", "·") for eq in self.differential_equations
        ]
        for i, eq in enumerate(differential_equations_formatted):
            for s_name in self.species:
                if f"dydt[V.{s_name.strip()}]" in eq:
                    eq = eq.replace(
                        f"dydt[V.{s_name.strip()}]",
                        f"|{i + 1:d}|d[{s_name.strip()}]/dt",
                    )
                    break
            for num in range(n_reaction):
                if f"v[{num + 1:d}]" in eq:
                    eq = eq.replace(
                        f"v[{num + 1:d}]",
                        f"_v_ <sub>{num + 1:d}</sub>",
                    )
            differential_equations_formatted[i] = eq + "|\n"
        with open(
            os.path.join("markdown", f"{self.name.split(os.sep)[-1]}", "differential_equation.md"),
            encoding="utf-8",
            mode="w",
        ) as f:
            f.writelines(
                [
                    "|No.|Differential equations|\n|---|----------------------|\n",
                    *differential_equations_formatted,
                ]
            )

    def register_word(self, rxn_rule: str, my_word: str) -> None:
        """
        Register user-defined rule word.

        Parameters
        ----------
        rxn_rule : str
            Define a rule to which users register a new rule word.

        my_word : str
            User-defined rule word.

        Examples
        --------
        >>> from pasmopy import Text2Model
        >>> mm_kinetics = Text2Model("michaelis_menten.txt")
        >>> mm_kinetics.register_word("is_dissociated", "releases")
        >>> mm_kinetics.convert()

        """
        if rxn_rule not in self.rule_words.keys():
            raise ValueError(
                f"{rxn_rule} is not defined in reaction_rules.\n"
                f"Choose a reaction rule from {', '.join(map(str, self.rule_words.keys()))}"
            )
        for rule, words in self.rule_words.items():
            for registered_word in words:
                if " " + my_word in registered_word and registered_word in " " + my_word:
                    raise NameError(
                        f"Cannot register '{my_word}'. "
                        f"Currently, it is used in the rule: {rule}"
                    )
        else:
            self.rule_words[rxn_rule].append(" " + my_word)
