import csv
import multiprocessing
import os
import platform
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd
import seaborn as sns
from biomass import Model, run_analysis, run_simulation
from scipy.integrate import simps
from tqdm import tqdm


@dataclass
class InSilico(object):
    """
    Patient-specific in silico models.

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
    biomass_kws : dict, optional
        Keyword arguments to pass to biomass.run_simulation.
    """

    biomass_kws: Optional[dict] = field(default=None)

    def _run_single_patient(self, patient: str) -> None:
        """
        Run a single patient-specifc model simulation.
        """

        kwargs = self.biomass_kws
        if kwargs is None:
            kwargs = {}
        kwargs.setdefault("viz_type", "average")
        kwargs.setdefault("show_all", False)
        kwargs.setdefault("stdev", True)
        kwargs.setdefault("save_format", "pdf")
        kwargs.setdefault("param_range", None)

        model = Model(".".join([self.path_to_models, patient.strip()])).create()
        run_simulation(model, **kwargs)

    def run(self, n_proc: Optional[int] = None) -> None:
        """
        Run simulations of multiple patient-specific models in parallel.

        Parameters
        ----------
        n_proc : int, optional (default: None)
            The number of worker processes to use.
        """
        if n_proc is None:
            n_proc = multiprocessing.cpu_count() - 1
        self.parallel_execute(self._run_single_patient, n_proc)

    @staticmethod
    def _calc_response_characteristics(
        time_course_data: np.ndarray,
        metric: str,
    ) -> str:
        if metric.lower() == "max":
            response_characteristics = np.max(time_course_data)
        elif metric.lower() == "auc":
            response_characteristics = simps(time_course_data)
        elif metric.lower() == "droprate":
            response_characteristics = (np.max(time_course_data) - time_course_data[-1]) / (
                len(time_course_data) - np.argmax(time_course_data)
            )
        else:
            raise ValueError("Available metrics are: 'max', 'AUC', 'droprate'.")

        return str(response_characteristics)

    def _extract(
        self,
        dynamic_characteristics: Dict[str, Dict[str, List[str]]],
        normalization: bool,
    ) -> None:
        """
        Extract response characteristics from patient-specific signaling dynamics.
        """
        os.makedirs("classification", exist_ok=True)
        for obs_name, conditions_and_metrics in dynamic_characteristics.items():
            with open(
                os.path.join("classification", f"{obs_name}.csv"),
                "w",
                newline="",
            ) as f:
                writer = csv.writer(f)
                header = ["Sample"]
                for condition, metrics in conditions_and_metrics.items():
                    for metric in metrics:
                        header.append(f"{condition}_{metric}")
                writer.writerow(header)

                for patient in tqdm(self.patients):
                    patient_specific = Model(
                        ".".join([self.path_to_models, patient.strip()])
                    ).create()
                    all_data = np.load(
                        os.path.join(
                            patient_specific.path,
                            "simulation_data",
                            "simulations_all.npy",
                        )
                    )
                    data = np.array(all_data[patient_specific.obs.index(obs_name)])
                    if normalization:
                        for i in range(data.shape[0]):
                            if not np.isnan(data[i]).all():
                                data[i] /= np.nanmax(data[i])
                        data = np.nanmean(data, axis=0)
                        data /= np.max(data)
                    patient_specific_characteristics = [patient]
                    for h in header[1:]:
                        condition, metric = h.split("_")
                        patient_specific_characteristics.append(
                            self._calc_response_characteristics(
                                data[:, patient_specific.sim.conditions.index(condition)],
                                metric,
                            )
                        )
                    writer = csv.writer(f, lineterminator="\n")
                    writer.writerow(patient_specific_characteristics)

    def subtyping(
        self,
        fname: Optional[str],
        dynamic_characteristics: Dict[str, Dict[str, List[str]]],
        normalization: bool = True,
        *,
        clustermap_kws: Optional[dict] = None,
    ):
        """
        Classify patients based on dynamic characteristics extracted from simulation results.

        Parameters
        ----------
        fname : str, path-like or None
            The clustermap is saved as fname if it is not None.

        dynamic_characteristics : Dict[str, Dict[str, List[str]]]
            {"observable": {"condition": ["metric", ...], ...}, ...}.
            Characteristics in the signaling dynamics used for classification.
            'metric' must be one of 'max', 'AUC', 'droprate'.

        normalization : bool (default: True)
            Whether to perform max-normalization.

        clustermap_kws : dict, optional (default: None)
            Keyword arguments to pass to seaborn.clustermap().

        Examples
        --------
        >>> with open ("models/breast/sample_names.txt", mode="r") as f:
        ...    TCGA_ID = f.read().splitlines()
        >>> from pasmopy import PatientModelSimulations
        >>> simulations = PatientModelSimulations("models.breast", TCGA_ID)
        >>> simulations.subtyping(
        ...    "subtype_classification.pdf",
        ...    {
        ...        "Phosphorylated_Akt": {"EGF": ["max"], "HRG": ["max"]},
        ...        "Phosphorylated_ERK": {"EGF": ["max"], "HRG": ["max"]},
        ...        "Phosphorylated_c-Myc": {"EGF": ["max"], "HRG": ["max"]},
        ...    },
        ...    clustermap_kws={"figsize": (9, 12)}
        ... )

        """
        # seaborn clustermap
        if clustermap_kws is None:
            clustermap_kws = {}
        clustermap_kws.setdefault("z_score", 1)
        clustermap_kws.setdefault("cmap", "RdBu_r")
        clustermap_kws.setdefault("center", 0)
        # extract response characteristics
        self._extract(dynamic_characteristics, normalization)
        if fname is not None:
            characteristics: List[pd.DataFrame] = []
            files = os.listdir("classification")
            for file in files:
                obs, ext = os.path.splitext(file)
                if ext == ".csv":
                    df = pd.read_csv(os.path.join("classification", file), index_col="Sample")
                    characteristics.append(
                        df.rename(columns=lambda s: obs.replace("_", " ") + "_" + s)
                    )
            all_info = pd.concat(characteristics, axis=1)
            all_info.index.name = ""
            fig = sns.clustermap(all_info, **clustermap_kws)
            fig.savefig(fname)


@dataclass
class PatientModelAnalyses(InSilico):
    """
    Run analyses of patient-specific models.

    Attributes
    ----------
    biomass_kws : dict, optional
        Keyword arguments to pass to biomass.run_analysis.
    """

    biomass_kws: Optional[dict] = field(default=None)

    def _run_single_patient(self, patient: str) -> None:
        """
        Run a single patient-specifc model analysis.
        """

        kwargs = self.biomass_kws
        if kwargs is None:
            kwargs = {}
        kwargs.setdefault("target", "initial_condition")
        kwargs.setdefault("metric", "integral")
        kwargs.setdefault("style", "heatmap")
        kwargs.setdefault("options", None)

        model = Model(".".join([self.path_to_models, patient.strip()])).create()
        run_analysis(model, **kwargs)

    def run(self, n_proc: Optional[int] = None) -> None:
        """
        Run analyses of multiple patient-specific models in parallel.

        Parameters
        ----------
        n_proc : int, optional (default: None)
            The number of worker processes to use.
        """
        if n_proc is None:
            n_proc = multiprocessing.cpu_count() - 1
        self.parallel_execute(self._run_single_patient, n_proc)
