import multiprocessing
import platform
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from biomass import ModelObject, run_analysis, run_simulation
from tqdm import tqdm

__all__ = ["PatientModelSimulations", "PatientModelAnalyses"]


@dataclass
class InSilico(object):
    """
    In silico patient models.

    Attributes
    ----------
    path_to_models : str
        Path (dot-separated) to the directory containing patient-specific models.

    patients : list of strings
        List of patients' names or identifiers.
    """

    path_to_models: str
    patients: List[str]

    def __post_init__(self) -> None:
        """
        Check for duplicates in self.patients.
        """
        duplicate = [patient for patient in set(self.patients) if self.patients.count(patient) > 1]
        if duplicate:
            raise NameError(f"Duplicate patient: {', '.join(duplicate)}")
        else:
            return None

    def import_model_package(self, patient: str) -> None:
        """
        Import biomass-formatted model package.

        Parameters
        ----------
        patient : str
            Name (ID) of each patient.
        """

        try:
            exec(
                f"from {self.path_to_models} import {patient.strip()}",
                globals(),
            )
        except ImportError:
            print(f"cannot import {patient.strip()} from {self.path_to_models}")

    def parallel_execute(
        self,
        func: Callable[[str], None],
        n_proc: int,
    ) -> None:
        """
        Execute multiple models in parallel.

        Parameters
        ----------
        func : Callable
            Function executing a single patient-specific model.

        n_proc : int
            The number of worker processes to use.
        """

        if platform.system() == "Darwin":
            # fork() has always been unsafe on Mac
            # spawn* functions should be instead
            ctx = multiprocessing.get_context("spawn")
            p = ctx.Pool(processes=n_proc)
        else:
            p = multiprocessing.Pool(processes=n_proc)

        with tqdm(total=len(self.patients)) as t:
            for _ in p.imap_unordered(func, self.patients):
                t.update(1)
        p.close()


@dataclass
class PatientModelSimulations(InSilico):
    """
    Run simulations of patient-specific models.

    Attributes
    ----------
    biomass_options : dict, optional
        Arguments of biomass.run_simulation.
    """

    biomass_options: Optional[dict] = field(default=None)

    def _run_single_patient(self, patient: str) -> None:
        """
        Run a single patient-specifc model simulation.

        Parameters
        ----------
        patient : str
            Name (ID) of each patient.
        """

        options = self.biomass_options
        if options is None:
            options = {}
        options.setdefault("viz_type", "average")
        options.setdefault("show_all", False)
        options.setdefault("stdev", True)
        options.setdefault("save_format", "pdf")
        options.setdefault("param_range", None)

        self.import_model_package(patient)

        model: ModelObject = eval(f"ModelObject({patient.strip()}.create())")
        run_simulation(model, **options)

    def run(self, n_proc: int = multiprocessing.cpu_count() - 1) -> None:
        """
        Run simulations of multiple patient-specific models in parallel.

        Parameters
        ----------
        n_proc : int (default: multiprocessing.cpu_count() - 1)
            The number of worker processes to use.
        """

        self.parallel_execute(self._run_single_patient, n_proc)


@dataclass
class PatientModelAnalyses(InSilico):
    """
    Run analyses of patient-specific models.

    Attributes
    ----------
    biomass_options : dict, optional
        Arguments of biomass.run_analysis.
    """

    biomass_options: Optional[dict] = field(default=None)

    def _run_single_patient(self, patient: str) -> None:
        """
        Run a single patient-specifc model analysis.

        Parameters
        ----------
        patient : str
            Name (ID) of each patient.
        """

        options = self.biomass_options
        if options is None:
            options = {}
        options.setdefault("target", "initial_condition")
        options.setdefault("metric", "integral")
        options.setdefault("style", "barplot")
        options.setdefault("options", None)

        self.import_model_package(patient)

        model: ModelObject = eval(f"ModelObject({patient.strip()}.create())")
        run_analysis(model, **options)

    def run(self, n_proc: int = multiprocessing.cpu_count() - 1) -> None:
        """
        Run analyses of multiple patient-specific models in parallel.

        Parameters
        ----------
        n_proc : int (default: multiprocessing.cpu_count() - 1)
            The number of worker processes to use.
        """

        self.parallel_execute(self._run_single_patient, n_proc)
