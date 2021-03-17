from dataclasses import dataclass, field
from typing import Dict, List

import pandas as pd


@dataclass
class Individualization(object):
    """
    Individualize a mechanistic model by incorporating gene expression levels.

    Attributes
    ----------
    parameters : List[str]
        List of model parameters.

    species : List[str]
        List of model species.

    tpm_values : str
        Path to (1) RLE-normalized and (2) post ComBat TPM values (CSV-formatted).

    structure : Dict[str, List[str]]
        Pairs of proteins and their related genes.

    prefix : str (default: "w_")
        Prefix of weighting factors on gene expression levels.
    """

    parameters: List[str]
    species: List[str]
    tpm_values: str
    structure: Dict[str, List[str]]
    prefix: str = field(default="w_", init=False)

    def __post_init__(self) -> None:
        self._tpm_rle_postComBat: pd.DataFrame = pd.read_csv(self.tpm_values, index_col=2)

    @property
    def tpm_rle_postComBat(self):
        return self._tpm_rle_postComBat

    def _get_tpm(self, gene: str, id: str) -> float:
        return self.tpm_rle_postComBat.at[gene, id]

    def _calculate_weighted_sum(
        self,
        id: str,
        x: List[float],
    ) -> Dict[str, float]:
        """
        Incorporate gene expression levels in the model.

        Parameters
        ----------
        id : str
            CCLE_ID or TCGA_ID.

        x : List[float]
            Model parameters.

        Returns
        -------
        weighted_sum : Dict[str, float]
            Estimated protein levels after incorporating transcriptomic data.
        """
        weighted_sum = dict.fromkeys(self.structure, 0.0)
        for (protein, genes) in self.structure.items():
            for gene in genes:
                weighted_sum[protein] += x[
                    self.parameters.index(self.prefix + gene)
                ] * self._get_tpm(gene, id)
        return weighted_sum

    def as_initial_condition(
        self,
        id: str,
        x: List[float],
        y0: List[float],
    ) -> List[float]:
        """
        Gene expression levels are incorporated as initial conditions.

        Parameters
        ----------
        id : str
            CCLE_ID or TCGA_ID.

        x : List[float]
            List of parameter values.

        y0 : List[float]
            List of initial values.

        Returns
        -------
        y0 (individualized) : List[float]
            Cell-line- or patient-specific initial conditions.
        """
        weighted_sum = self._calculate_weighted_sum(id, x)
        for protein in self.structure.keys():
            y0[self.species.index(protein)] *= weighted_sum[protein]
        return y0

    def as_maximal_transcription_rate(
        self,
        id: str,
        x: List[float],
        param_name: str,
        protein: str,
    ) -> float:
        """
        Gene expression levels are incorporated as maximal transcription rates.
        """
        weighted_sum = self._calculate_weighted_sum(id, x)
        x[self.parameters.index(param_name)] *= weighted_sum[protein]
        return x[self.parameters.index(param_name)]
