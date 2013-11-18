# -*- coding: utf-8 -*-
# Filename: data.py
""" Module for importing and pre-processing of tomographic data.
"""
import numpy as np
from scipy import ndimage
from dataio import hdf5
from scipy.optimize import minimize
from tomoRecon import tomoRecon
from dataio import tiff
import constants
import pywt
import shutil
import os


class read(object):
    def __init__(self,
                 inputFile,
                 projectionsStart=None,
                 projectionsEnd=None,
                 projectionsStep=None,
                 slicesStart=None,
                 slicesEnd=None,
                 slicesStep=None,
                 pixelsStart=None,
                 pixelsEnd=None,
                 pixelsStep=None,
                 whiteStart=None,
                 whiteEnd=None,
                 darkStart=None,
                 darkEnd=None):
        """ Constructs the read options.

        Parameters
        ----------
        inputFile : str
            Input file.

        projectionsStart, projectionsEnd, projectionsStep : scalar, optional
            Values of the start, end and step of the projections to
            be used for slicing for the whole ndarray.

        slicesStart, slicesEnd, slicesStep : scalar, optional
            Values of the start, end and step of the slices to
            be used for slicing for the whole ndarray.

        pixelsStart, pixelsEnd, pixelsStep : scalar, optional
            Values of the start, end and step of the pixels to
            be used for slicing for the whole ndarray.

        whiteStart, whiteEnd : scalar, optional
            Values of the start, end and step of the
            slicing for the whole white field shots.

        darkStart, darkEnd : scalar, optional
            Values of the start, end and step of the
            slicing for the whole dark field shots.
        """
        print "Reading data..."

        # Input parameters
        self.inputFile = inputFile

        # Read data from exchange group.
        self.data = hdf5.read(inputFile,
                            arrayName='exchange/data',
                            projectionsStart=projectionsStart,
                            projectionsEnd=projectionsEnd,
                            projectionsStep=projectionsStep,
                            slicesStart=slicesStart,
                            slicesEnd=slicesEnd,
                            slicesStep=slicesStep,
                            pixelsStart=pixelsStart,
                            pixelsEnd=pixelsEnd,
                            pixelsStep=pixelsStep).astype('float')

        # Read white field data from exchange group.
        self.white = hdf5.read(inputFile,
                            arrayName='exchange/data_white',
                            projectionsStart=whiteStart,
                            projectionsEnd=whiteEnd,
                            slicesStart=slicesStart,
                            slicesEnd=slicesEnd,
                            slicesStep=slicesStep,
                            pixelsStart=pixelsStart,
                            pixelsEnd=pixelsEnd,
                            pixelsStep=pixelsStep).astype('float')

        # Read dark field data from exchange group.
        self.dark = hdf5.read(inputFile,
                            arrayName='exchange/data_dark',
                            projectionsStart=darkStart,
                            projectionsEnd=darkEnd,
                            slicesStart=slicesStart,
                            slicesEnd=slicesEnd,
                            slicesStep=slicesStep,
                            pixelsStart=pixelsStart,
                            pixelsEnd=pixelsEnd,
                            pixelsStep=pixelsStep).astype('float')

        # Assign the rotation center.
        self.center = self.data.shape[2] / 2

        # Assign angles.
        self.angles = None


    def normalize(self, cutoff=None):
        """ Normalize using average white field images.
        """
        print "Normalizing data..."
        avgWhite = np.mean(self.white, axis=0)
        for m in range(self.data.shape[0]):
            self.data[m, :, :] = np.divide(self.data[m, :, :], avgWhite)

        if cutoff is not None:
            self.data[self.data > cutoff] = cutoff


    def medianFilter(self, axis=1, size=(1, 3)):
        """ Apply median filter to data.

        Parameters
        ----------
        axis : scalar, optional
            Specifies the axis that for filtering.
            0: slices-pixels plane
            1: projections-pixels plane
            2: projections-slices plans

        size : array-like, optional
           The size of the filter.
        """
        print "Applying median filter to data..."

        # Override medianaxis if one dimension is null.
        if self.data.shape[0] == 1:
            axis = 0
        elif self.data.shape[1] == 1:
            axis = 1
        elif self.data.shape[2] == 1:
            axis = 2

        if axis is 0:
            for m in range(self.data.shape[0]):
                self.data[m, :, :] = ndimage.filters.median_filter(
                                     np.squeeze(self.data[m, :, :]),
                                     size=size)
        elif axis is 1:
            for m in range(self.data.shape[1]):
                self.data[:, m, :] = ndimage.filters.median_filter(
                                     np.squeeze(self.data[:, m, :]),
                                     size=size)
        elif axis is 2:
            for m in range(self.data.shape[2]):
                self.data[:, :, m] = ndimage.filters.median_filter(
                                     np.squeeze(self.data[:, :, m]),
                                     size=size)
        else: raise ValueError('Check median filter axes.')


    def diagnoseCenter(self,
                       sliceNo=None,
                       centerStart=None,
                       centerEnd=None,
                       centerStep=None):
        """ Diagnostic tools to find rotation center.

        Helps finding the rotation center manually by
        visual inspection of the selected reconstructions
        with different centers. The outputs for different
        centers are put into ``data/diagnose`` directory
        and the corresponding center positions are printed
        so that one can skim through the images and
        select the best.

        Parameters
        ----------
        sliceNo : scalar, optional
            The index of the slice to be used for diagnostics.
            Default is the central slice.

        centerStart, centerEnd, centerStep : scalar, optional
            Values of the start, end and step of the center values to
            be used for diagnostics.
        """
        print "Diagnosing rotation center..."
        numProjections =  self.data.shape[0]
        numSlices =  self.data.shape[1]
        numPixels =  self.data.shape[2]

        if sliceNo is None:
            sliceNo = numSlices / 2
        if centerStart is None:
            centerStart = (numPixels / 2) - 20
        if centerEnd is None:
            centerEnd = (numPixels / 2) + 20
        if centerStep is None:
            centerStep = 1

        sliceData = self.data[:, sliceNo, :]
        center = np.arange(centerStart, centerEnd, centerStep)
        numCenter = center.size
        stackedSlices = np.zeros((numProjections, numCenter, numPixels),
                                dtype='float')
        for m in range(numCenter):
            stackedSlices[:, m, :] = sliceData
        dataset = createDataObject(stackedSlices, center=center)
        recon = tomoRecon.tomoRecon(dataset)
        recon.run(dataset, printInfo=False)
        if os.path.isdir('data/diagnose'):
            shutil.rmtree('data/diagnose')
        tiff.write(recon.data, outputFile='data/diagnose/center_.tiff',)
        for m in range(numCenter):
            print 'Center for data/diagnose/xxx' + str(m) + '.tiff: ' + str(center[m])


    def optimizeCenter(self,
                       sliceNo=None,
                       inCenter=None,
                       histMin=None,
                       histMax=None,
                       tol=0.5,
                       filterSigma=2):
        """ Finds the best rotation center for tomographic reconstruction
        using the tomo_recon reconstruction code. This is done by
        ''Nelder-Mead'' routine of the scipy optimization module and
        the cost function is based on image entropy. The optimum
        rotation center is the one that produces the minimum image entropy.

        This code is the python version of optimize_center.pro written
        by Mark Rivers with some slight modifications. In this version low
        pass filtering feature is added to cope with edgy-images.

        Parameters
        ----------
        reconInput : ndarray, shape(numProjections, numSlices, numPixels)
            An array of normalized projections.

        sliceNo : scalar, optional
            The index of the slice to be used for finding optimal center.
            Default is the central slice.

        inCenter : scalar, optional
            The initial guess for the center. Default is half ot the number
            of pixels.

        histMin : scalar, optional
            The minimum reconstructed value to be used when computing
            the histogram to compute the entropy. The default is the half
            minimum value of the central slice.

        histMax : scalar, optional
            The maximum reconstructed value to be used when computing the
            histogram to compute the entropy. The default is the twice
            maximum value of the central slice.

        tol : scalar, optional
            Desired sub-pixel accuracy. Default is 1.

        filterSigma : scalar, optional
            Standard variation of the low pass filter. Default is ``1``.
            This is used for image denoising. Value can be higher for
            datasets having high frequency components
            (e.g., phase-contrast images). Higher values
            increase computation time.

        Returns
        -------
        optimalCenter : scalar
            This function returns the index of the center position that
            results in the minimum entropy in the reconstructed image.
        """
        print "Opimizing rotation center using Nelder-Mead method..."
        numSlices =  self.data.shape[1]
        numPixels =  self.data.shape[2]

        if sliceNo is None:
            sliceNo = numSlices / 2
        elif sliceNo > numSlices:
            raise ValueError('sliceNo is higher than number of available slices.')

        if inCenter is None:
            inCenter = numPixels / 2
        elif not np.isscalar(inCenter) :
            raise ValueError('inCenter must be a scalar.')

        #selectedSlice = np.expand_dims(selectedSlice, axis=1)
        recon = tomoRecon.tomoRecon(self)
        recon.run(self, sliceNo=sliceNo, printInfo=False)
        if histMin is None:
            histMin = np.min(recon.data)
            if histMin < 0:
                histMin = 2 * histMin
            elif histMin >= 0:
                histMin = 0.5 * histMin

        if histMax is None:
            histMax = np.max(recon.data)
            if histMax < 0:
                histMax = 0.5 * histMax
            elif histMax >= 0:
                histMax = 2 * histMax

        res = minimize(read._costFunc,
                    inCenter,
                    args=(self, recon, sliceNo, histMin, histMax, filterSigma),
                    method='Nelder-Mead',
                    tol=tol,
                    options={'disp':True})

        print 'Calculated rotation center : ' + str(np.squeeze(res.x))
        print '------------------------------------------------'
        return res.x

    @staticmethod
    def _costFunc(center, reconInput, recon, sliceNo, histMin, histMax, filterSigma):
        """ Cost function of the ``optimizeCenter``.
        """
        reconInput.center = center
        recon.run(reconInput, sliceNo=sliceNo, printInfo=False)
        histr, e = np.histogram(ndimage.filters.gaussian_filter(recon.data,
                                                            sigma=filterSigma),
                                bins=64, range=[histMin, histMax])
        histr = histr.astype('float64') / recon.data.size + 1e-12
        print 'Current center : ' + str(np.squeeze(center))
        return -np.dot(histr, np.log2(histr))
        

    def retrievePhasePaganin(self, pixelSize, dist, energy, deltaOverMu=1e-8):
        """ Perform single-material phase retrieval
        according to Paganin's method.

        Parameters
        ----------
        data : ndarray, shape(numProjections, numSlices, numPixels)
            A stack of flat-field corrected projections.

        pixelSize : scalar
            Detector pixel size in cm.

        dist : scalar
            Propagation distance of x-rays in cm.

        energy : scalar
            Energy of x-rays in keV.

        deltaOverMu : scalar
            Ratio of the imaginary part of the refractive index
            decrement to the attenuation of the material.

        Returns
        -------
        phase : ndarray
            Retrieved phase.

        References
        ----------
        - J. of Microscopy, Vol 206(1), 33-40(2001)
        """
        print "Retrieving phase..."
        # Size of the detector
        numProjections, numSlices, numPixels = self.data.shape

        # Sampling in reciprocal space.
        indx = (1 / ((numSlices - 1) * pixelSize)) * \
                np.arange(-(numSlices-1)*0.5, numSlices*0.5)
        indy = (1 / ((numPixels - 1) * pixelSize)) * \
                np.arange(-(numPixels-1)*0.5, numPixels*0.5)
        du, dv = np.meshgrid(indy, indx)
        w2 = np.square(du) + np.square(dv)

        # Fourier transform of data.
        for m in range(numProjections):
            fftData = np.fft.fftshift(tomoRecon.fftw2d(self.data[m, : ,:], direction='forward'))
            H = 1 / (4 * np.square(constants.PI) * dist * deltaOverMu * w2 + 1)
            filteredData = np.fft.ifftshift(np.multiply(H, fftData))
            self.data[m, : ,:] = -deltaOverMu * np.log(np.real(tomoRecon.fftw2d(filteredData, direction='backward')))


    def retrievePhaseBronnikov(self, pixelSize, dist, energy, alpha=0.5):
        """ Perform Bronnikov-type phase retrieval.

        Parameters
        ----------
        data : ndarray, shape(numProjections, numSlices, numPixels)
            A stack of flat-field corrected projections.

        pixelSize : scalar
            Detector pixel size in cm.

        dist : scalar
            Propagation distance of x-rays in cm.

        energy : scalar
            Energy of x-rays in keV.

        Returns
        -------
        phase : ndarray
            Retrieved phase.
        """
        print "Retrieving phase..."
        # Size of the detector
        numProjections, numSlices, numPixels = self.data.shape

        # Wavelength of x-rays.
        wavelength = (2 * constants.PI *
                    constants.PLANCK_CONSTANT *
                    constants.SPEED_OF_LIGHT) / energy

        # Sampling in reciprocal space.
        indx = (1 / ((numSlices - 1) * pixelSize)) * \
                np.arange(-(numSlices-1)*0.5, numSlices*0.5)
        indy = (1 / ((numPixels - 1) * pixelSize)) * \
                np.arange(-(numPixels-1)*0.5, numPixels*0.5)
        du, dv = np.meshgrid(indy, indx)
        w2 = np.square(du) + np.square(dv)

        # Right-hand side term:
        self.data = 1 - self.data

        # Fourier transform of data.
        for m in range(numProjections):
            fftData = np.fft.fftshift(tomoRecon.fftw2d(self.data[m, : ,:], direction='forward'))
            H = 1 / (2 * constants.PI * wavelength * dist * w2 + alpha)
            filteredData = np.fft.ifftshift(np.multiply(H, fftData))
            self.data[m, : ,:] = 1-np.real(tomoRecon.fftw2d(filteredData, direction='backward'))



    def removeRings(self, level=6, wname='db10', sigma=2):
        """ Remove ring artifacts.

        Parameters
        ----------
        level : scalar, optional
            Number of DWT levels.

        wname : str, optional
            Type of the wavelet filter.

        sigma : scalar, optional
            Damping parameter in Fourier space.

        References
        ----------
        - Optics Express, Vol 17(10), 8567-8591(2009)
        """
        print "Removing rings..."
        for m in range(self.data.shape[1]):
            # Wavelet decomposition.
            im = self.data[:, m, :]
            cH = []
            cV = []
            cD = []
            for m in range(level):
                im, (cHt, cVt, cDt) = pywt.dwt2(im, wname)
                cH.append(cHt)
                cV.append(cVt)
                cD.append(cDt)

            # FFT transform of horizontal frequency bands
            for m in range(level):
                # FFT
                fcV = np.fft.fftshift(np.fft.fft(cV[m], axis=0))
                my, mx = fcV.shape

                # Damping of ring artifact information.
                y_hat = (np.arange(-my, my, 2, dtype='float')+1) / 2
                damp = 1 - np.exp(-np.power(y_hat, 2) / (2 * np.power(sigma, 2)))
                fcV = np.multiply(fcV, np.transpose(np.tile(damp, (mx, 1))))

                # Inverse FFT.
                cV[m] = np.real(np.fft.ifft(np.fft.ifftshift(fcV), axis=0))

            # Wavelet reconstruction.
            nim = im
            for m in range(level)[::-1]:
                nim = nim[0:cH[m].shape[0], 0:cH[m].shape[1]]
                nim = pywt.idwt2((nim, (cH[m], cV[m], cD[m])), wname)
            nim = nim[0:self.data.shape[0], 0:self.data.shape[2]]
            self.data[:, m, :] = nim
            
            
    def correctView(self, numOverlapPixels=0):
        """ Stich 180-360 degree projections on 0-180 degree
        projections. This is usually the case when field
        of view of the detector is smaller than the
        object to be imaged.

        Parameters
        ----------
        numOverlapPixels : scalar, optional
            The overlapping regions between 0-180 and 180-360
            degree projections.
        """
        print "Correcting field of view..."
        numProjections, numSlices, numPixels = self.data.shape

        if numProjections % 2 != 0: # if odd
            imgFirstHalf = self.data[1:numProjections/2 + 1, :, numOverlapPixels:numPixels]
            imgSecondHalf = self.data[numProjections/2:numProjections - 1]
        else:
            imgFirstHalf = self.data[1:numProjections/2 + 1, :, numOverlapPixels:numPixels]
            imgSecondHalf = self.data[numProjections/2:numProjections]

        ind = range(0, numPixels)[::-1]
        self.data = np.c_[imgSecondHalf[:, :, ind], imgFirstHalf]
        

class createDataObject(object):
    """ Creates data object.
    """
    def __init__(self, data, white=None, dark=None, center=None, angles=None):
        self.data = np.array(data)
        if white is None:
            self.white = None
        else: self.white = white
        if dark is None:
            self.dark = None
        else: self.dark = dark
        if center is None:
            self.center = data.shape[2] / 2
        else: self.center = center
        if angles is None:
            self.angles = None
        else: self.angles = angles
