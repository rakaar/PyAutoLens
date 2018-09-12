from autolens.imaging import imaging_util
from autolens.imaging import image
from autolens.imaging import mask
from autolens.lensing import ray_tracing
from autolens.lensing import galaxy as g
from autolens.profiles import light_profiles as lp
from autolens.profiles import mass_profiles as mp
import matplotlib.pyplot as plt
import os

# In this example, we'll simulate a lensed source galaxy and output the images (as .fits). This image is used to
# demonstrate lens modeling in example/phase/1_basic.py.

# First, lets setup the PSF we are going to blur our simulated image with, using a Gaussian profile on an 11x11 grid.
psf = image.PSF.simulate_as_gaussian(shape=(11, 11), sigma=0.75)
# plt.imshow(psf)
# plt.show()

# We need to set up the grids of Cartesian coordinates we will use to perform ray-tracing. The function below
# sets these grids up using the shape and pixel-scale of the image we will ultimately simulate. The PSF shape is
# required to ensure that edge-effects do not impact PSF blurring later in the simulation.
imaging_grids = mask.ImagingGrids.padded_grids_for_simulation(shape=(100, 100), pixel_scale=0.1, psf_shape=psf.shape)

# Use the 'galaxy' module (imported as 'g'), 'light_profiles' module (imported as 'lp') and 'mass profiles' module
# (imported as 'mp') to setup the lens and source galaxies.
#
# For the lens galaxy, we'll use a singular isothermal ellipsoid (SIE) mass profile.
lens_galaxy = g.Galaxy(mass=mp.EllipticalIsothermal(centre=(0.01, 0.01), axis_ratio=0.8, phi=40.0, einstein_radius=1.8))

# And for the source galaxy an elliptical Exponential profile.
source_galaxy = g.Galaxy(light=lp.EllipticalExponential(centre=(0.01, 0.01), axis_ratio=0.9, phi=90.0, intensity=0.5,
                                                        effective_radius=0.3))

# Next, we pass these galaxies into the 'ray_tracing' module, here using a 'TracerImageSourcePlanes' which represents
# ray-tracer which has both an image and source plane.

# Using the lens galaxy's mass profile(s), this tracer automatically computes the deflection angles of light on the
# imaging grids and traces their coordinates to the source-plane
tracer = ray_tracing.TracerImageSourcePlanes(lens_galaxies=[lens_galaxy], source_galaxies=[source_galaxy],
                                             image_grids=imaging_grids)

# In example/howtolens/ray_tracing, we'll discuss the in-built properties a tracer has describing the lens system.

# For this example, we'll just extract its 2d image-plane image - lets have a look!
#plt.imshow(tracer.image_plane_image_2d)
#plt.show()

# To simulate the image, we pass this image to the imaging module's simulate function. We add various effects, including
# PSF blurring, the background sky and noise.
image_simulated = image.PreparatoryImage.simulate(array=tracer.image_plane_image_2d, pixel_scale=0.1,
                                                  exposure_time=300.0, psf=psf, background_sky_level=0.1,
                                                  add_noise=True)
plt.imshow(image_simulated.noise_map)
plt.show()

# Finally, lets output these files to.fits so that we can fit them in the phase and pipeline examples
path = "{}".format(os.path.dirname(os.path.realpath(__file__))) # Setup path so we can output the simulated data.
imaging_util.numpy_array_to_fits(array=image_simulated, path=path+'/../data/basic/image.fits')
imaging_util.numpy_array_to_fits(array=image_simulated.noise_map, path=path + '/../data/basic/noise_map.fits')
imaging_util.numpy_array_to_fits(array=psf, path=path+'/../data/basic/psf.fits')