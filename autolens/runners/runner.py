import os

from autolens import conf
from autolens.imaging import image
from autolens.imaging import scaled_array
from autolens.runners.lens_and_source import initializer

dirpath = os.path.dirname(os.path.realpath(__file__))
conf.instance.output_path = os.path.expanduser("~/")


def load_image(data_name, pixel_scale, image_hdu, noise_hdu, psf_hdu, psf_trimmed_shape=None,
               effective_exposure_time=None):
    data_dir = "{}/../data/{}".format(dirpath, data_name)

    data = scaled_array.ScaledSquarePixelArray.from_fits_with_scale(file_path=data_dir, hdu=image_hdu,
                                                                    pixel_scale=pixel_scale)
    data = data.trim_around_centre((301, 301))
    background_noise = scaled_array.ScaledSquarePixelArray.from_fits_with_scale(file_path=data_dir, hdu=noise_hdu,
                                                                                pixel_scale=pixel_scale)
    background_noise = background_noise.trim_around_centre((301, 301))
    psf = image.PSF.from_fits_with_scale(file_path=data_dir, hdu=psf_hdu, pixel_scale=pixel_scale)
    if psf_trimmed_shape is not None:
        psf = psf.trim_around_centre(psf_trimmed_shape)

    if isinstance(effective_exposure_time, float):
        effective_exposure_time = scaled_array.ScaledSquarePixelArray.single_value(value=effective_exposure_time,
                                                                                   shape=data.shape,
                                                                                   pixel_scale=pixel_scale)

    return image.PreparatoryImage(array=data, pixel_scale=pixel_scale, psf=psf, background_noise_map=background_noise,
                                  effective_exposure_map=effective_exposure_time)


im = load_image(data_name='slacs05_bg/slacs_4_post.fits', pixel_scale=0.05, image_hdu=1, noise_hdu=2, psf_hdu=3,
                psf_trimmed_shape=(41, 41), effective_exposure_time=288.0)

im.background_noise_map = 1.0 / im.background_noise_map
im.noise_map = im.estimated_noise_map
pipeline = initializer.make()
pipeline.run(im)
