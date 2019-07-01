import copy

import numpy as np
from typing import cast

import autofit as af
from autolens import exc
from autolens.lens import lens_data as ld, lens_fit
from autolens.model.galaxy import galaxy as g
from autolens.model.inversion import pixelizations as px
from autolens.model.inversion import regularization as rg
from autolens.pipeline.phase import phase as ph
from autolens.pipeline.phase import phase_imaging
from autolens.pipeline.phase.phase import setup_phase_mask
from autolens.pipeline.plotters import hyper_plotters


class HyperPhase(object):
    def __init__(self, phase: ph.Phase):
        """
        Abstract HyperPhase. Wraps a regular phase, performing that phase before performing the action
        specified by the run_hyper.

        Parameters
        ----------
        phase
            A regular phase
        """
        self.phase = phase

    @property
    def hyper_name(self) -> str:
        """
        The name of the hyper form of the phase. This is used to generate folder names and also address the
        hyper results in the Result object.
        """
        raise NotImplementedError()

    def run_hyper(self, *args, **kwargs) -> af.Result:
        """
        Run the hyper phase.

        Parameters
        ----------
        args
        kwargs

        Returns
        -------
        result
            The result of the hyper phase.
        """
        raise NotImplementedError()

    def make_hyper_phase(self) -> ph.Phase:
        """
        Returns
        -------
        hyper_phase
            A copy of the original phase with a modified name and path
        """
        phase = copy.deepcopy(self.phase)
        phase.phase_path = f"{phase.phase_path}/{phase.phase_name}"
        phase.phase_name = self.hyper_name
        return phase

    def run(self, data, results: af.ResultsCollection = None, **kwargs) -> af.Result:
        """
        Run the normal phase and then the hyper phase.

        Parameters
        ----------
        data
            Data
        results
            Results from previous phases.
        kwargs

        Returns
        -------
        result
            The result of the phase, with a hyper result attached as an attribute with the hyper_name of this
            phase.
        """
        results = copy.deepcopy(results) if results is not None else af.ResultsCollection()
        result = self.phase.run(
            data,
            results=results,
            **kwargs
        )
        results.add(self.phase.phase_name, result)
        hyper_result = self.run_hyper(
            data=data,
            results=results,
            **kwargs
        )
        setattr(result, self.hyper_name, hyper_result)
        return result


# noinspection PyAbstractClass
class VariableFixingHyperPhase(HyperPhase):
    def __init__(
            self,
            phase: ph.Phase,
            variable_classes=tuple()
    ):
        super().__init__(phase)
        self.variable_classes = variable_classes

    def run_hyper(self, data, results=None, **kwargs):
        """
        Run the phase, overriding the optimizer's variable instance with one created to
        only fit pixelization hyperparameters.
        """
        variable = copy.deepcopy(results.last.variable)
        self.transfer_classes(
            results.last.constant,
            variable
        )
        phase = self.make_hyper_phase()
        phase.optimizer.variable = variable

        return phase.run(
            data,
            results=results,
            **kwargs
        )

    def transfer_classes(self, instance, mapper):
        """
        Recursively overwrite priors in the mapper with constant values from the
        instance except where the containing class is the decedent of a listed class.

        Parameters
        ----------
        instance
            The best fit from the previous phase
        mapper
            The prior variable from the previous phase
        """
        for key, instance_value in instance.__dict__.items():
            try:
                mapper_value = getattr(mapper, key)
                if isinstance(mapper_value, af.Prior):
                    setattr(mapper, key, instance_value)
                if not any(
                        isinstance(
                            instance_value,
                            cls
                        )
                        for cls in self.variable_classes
                ):
                    try:
                        self.transfer_classes(
                            instance_value,
                            mapper_value)
                    except AttributeError:
                        setattr(mapper, key, instance_value)
            except AttributeError:
                pass


class HyperPixelizationPhase(VariableFixingHyperPhase):
    """
    Phase that makes everything in the variable from the previous phase equal to the
    corresponding value from the best fit except for variables associated with
    pixelization
    """

    def __init__(self, phase: ph.Phase):
        super().__init__(
            phase,
            variable_classes=(
                px.Pixelization,
                rg.Regularization
            )
        )

    @property
    def hyper_name(self):
        return "pixelization"

    @property
    def uses_inversion(self):
        return True

    @property
    def uses_hyper_images(self):
        return True

    class Analysis(phase_imaging.LensSourcePlanePhase.Analysis):

        def figure_of_merit_for_fit(self, tracer):
            pass

        def __init__(self, lens_data, cosmology, positions_threshold, results=None,
                     uses_hyper_images=False):
            super(HyperPixelizationPhase.Analysis, self).__init__(
                lens_data=lens_data, cosmology=cosmology,
                positions_threshold=positions_threshold,
                results=results, uses_hyper_images=uses_hyper_images)


class HyperGalaxyPhase(HyperPhase):
    @property
    def hyper_name(self):
        return "hyper_galaxy"

    class Analysis(af.Analysis):

        def __init__(self, lens_data, model_image_2d, galaxy_image_2d):
            """
            An analysis to fit the noise for a single galaxy image.
            Parameters
            ----------
            lens_data: LensData
                Lens data, including an image and noise
            model_image_2d: ndarray
                An image produce of the overall system by a model
            galaxy_image_2d: ndarray
                The contribution of one galaxy to the model image
            """
            self.lens_data = lens_data

            self.hyper_model_image_1d = lens_data.array_1d_from_array_2d(
                array_2d=model_image_2d)
            self.hyper_galaxy_image_1d = lens_data.array_1d_from_array_2d(
                array_2d=galaxy_image_2d)

            self.check_for_previously_masked_values(array=self.hyper_model_image_1d)
            self.check_for_previously_masked_values(array=self.hyper_galaxy_image_1d)

            self.plot_hyper_galaxy_subplot = \
                af.conf.instance.visualize.get('plots', 'plot_hyper_galaxy_subplot',
                                               bool)

        @staticmethod
        def check_for_previously_masked_values(array):
            if not np.all(array) != 0.0:
                raise exc.PhaseException(
                    'When mapping a 2D array to a 1D array using lens data, a value '
                    'encountered was 0.0 and therefore masked in a previous phase.')

        def visualize(self, instance, image_path, during_analysis):

            if self.plot_hyper_galaxy_subplot:
                hyper_model_image_2d = self.lens_data.map_to_scaled_array(
                    array_1d=self.hyper_model_image_1d)
                hyper_galaxy_image_2d = self.lens_data.map_to_scaled_array(
                    array_1d=self.hyper_galaxy_image_1d)

                hyper_galaxy = instance.hyper_galaxy

                contribution_map_2d = hyper_galaxy.contribution_map_from_hyper_images(
                    hyper_model_image=hyper_model_image_2d,
                    hyper_galaxy_image=hyper_galaxy_image_2d)

                fit_normal = lens_fit.LensDataFit(
                    image_1d=self.lens_data.image_1d,
                    noise_map_1d=self.lens_data.noise_map_1d,
                    mask_1d=self.lens_data.mask_1d,
                    model_image_1d=self.hyper_model_image_1d,
                    map_to_scaled_array=self.lens_data.map_to_scaled_array)

                fit = self.fit_for_hyper_galaxy(hyper_galaxy=hyper_galaxy)

                hyper_plotters.plot_hyper_galaxy_subplot(
                    hyper_galaxy_image=hyper_galaxy_image_2d,
                    contribution_map=contribution_map_2d,
                    noise_map=self.lens_data.noise_map_2d,
                    hyper_noise_map=fit.noise_map_2d,
                    chi_squared_map=fit_normal.chi_squared_map_2d,
                    hyper_chi_squared_map=fit.chi_squared_map_2d,
                    output_path=image_path, output_format='png')

        def fit(self, instance):
            """
            Fit the model image to the real image by scaling the hyper noise.
            Parameters
            ----------
            instance: ModelInstance
                A model instance with a hyper galaxy property
            Returns
            -------
            fit: float
            """
            fit = self.fit_for_hyper_galaxy(hyper_galaxy=instance.hyper_galaxy)
            return fit.figure_of_merit

        def fit_for_hyper_galaxy(self, hyper_galaxy):

            hyper_noise_1d = hyper_galaxy.hyper_noise_map_from_hyper_images_and_noise_map(
                hyper_model_image=self.hyper_model_image_1d,
                hyper_galaxy_image=self.hyper_galaxy_image_1d,
                noise_map=self.lens_data.noise_map_1d)

            hyper_noise_map_1d = self.lens_data.noise_map_1d + hyper_noise_1d

            return lens_fit.LensDataFit(
                image_1d=self.lens_data.image_1d,
                noise_map_1d=hyper_noise_map_1d,
                mask_1d=self.lens_data.mask_1d,
                model_image_1d=self.hyper_model_image_1d,
                map_to_scaled_array=self.lens_data.map_to_scaled_array)

        @classmethod
        def describe(cls, instance):
            return "Running hyper galaxy fit for HyperGalaxy:\n{}".format(
                instance.hyper_galaxy)

    def run_hyper(self, data, results=None, mask=None, positions=None):
        """
        Run a fit for each galaxy from the previous phase.
        Parameters
        ----------
        data: LensData
        results: ResultsCollection
            Results from all previous phases
        mask: Mask
            The mask
        positions
        Returns
        -------
        results: HyperGalaxyResults
            A collection of results, with one item per a galaxy
        """
        phase = self.make_hyper_phase()

        mask = setup_phase_mask(
            data=data,
            mask=mask,
            mask_function=cast(phase_imaging.PhaseImaging, phase).mask_function,
            inner_mask_radii=cast(phase_imaging.PhaseImaging, phase).inner_mask_radii
        )

        lens_data = ld.LensData(
            ccd_data=data,
            mask=mask,
            sub_grid_size=cast(phase_imaging.PhaseImaging, phase).sub_grid_size,
            image_psf_shape=cast(phase_imaging.PhaseImaging, phase).image_psf_shape,
            positions=positions,
            interp_pixel_scale=cast(phase_imaging.PhaseImaging, phase).interp_pixel_scale,
            uses_inversion=cast(phase_imaging.PhaseImaging, phase).uses_inversion
        )

        model_image_2d = results.last.most_likely_fit.model_image_2d

        hyper_result = copy.deepcopy(results.last)
        hyper_result.analysis.uses_hyper_images = True
        hyper_result.analysis.hyper_model_image_1d = lens_data.array_1d_from_array_2d(
            array_2d=model_image_2d
        )
        hyper_result.analysis.hyper_galaxy_image_1d_path_dict = dict()

        for galaxy_path, galaxy in results.last.path_galaxy_tuples:

            optimizer = phase.optimizer.copy_with_name_extension(
                extension=galaxy_path[-1])
            optimizer.variable.hyper_galaxy = g.HyperGalaxy
            galaxy_image_2d = results.last.image_2d_dict[galaxy_path]

            # If array is all zeros, galaxy did not have image in previous phase and
            # should be ignored
            if not np.all(galaxy_image_2d == 0):
                hyper_result.analysis.hyper_galaxy_image_1d_path_dict[
                    galaxy_path
                ] = lens_data.array_1d_from_array_2d(
                    array_2d=galaxy_image_2d
                )
                analysis = self.Analysis(
                    lens_data=lens_data,
                    model_image_2d=model_image_2d,
                    galaxy_image_2d=galaxy_image_2d
                )
                result = optimizer.fit(analysis)

                hyper_result.constant.object_for_path(
                    galaxy_path
                ).hyper_galaxy = result.constant.hyper_galaxy

        return hyper_result


class CombinedHyperPhase(ph.Phase):
    def __init__(
            self,
            phase: ph.Phase,
            hyper_phase_classes: (type,) = tuple()
    ):
        """
        A combined hyper phase that can run zero or more other hyper phases after the initial phase is run.

        Parameters
        ----------
        phase
            The phase wrapped by this hyper phase
        hyper_phase_classes
            The classes of hyper phases to be run following the initial phase
        """
        super().__init__(
            phase_name=phase.phase_name
        )
        self.hyper_phases = list(map(
            lambda cls: cls(
                phase
            ),
            hyper_phase_classes
        ))
        self.phase = phase

    def run(self, data, results: af.ResultsCollection = None, **kwargs) -> af.Result:
        """
        Run the regular phase followed by the hyper phases. Each result of a hyper phase is attached to the
        overall result object by the hyper_name of that phase.

        Parameters
        ----------
        data
            The data
        results
            Results from previous phases
        kwargs

        Returns
        -------
        result
            The result of the regular phase, with hyper results attached by associated hyper names
        """
        results = copy.deepcopy(results) if results is not None else af.ResultsCollection()
        result = self.phase.run(
            data,
            results=results,
            **kwargs
        )
        results.add(self.phase.phase_name, result)

        for hyper_phase in self.hyper_phases:
            hyper_result = hyper_phase.run_hyper(
                data=data,
                results=results,
                **kwargs
            )
            setattr(result, hyper_phase.hyper_name, hyper_result)
        return result
