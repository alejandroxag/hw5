# Image Super-Resolution
## 11685 - Introduction to Deep Learning

> Image x4 upscaling using Autoencoder, SRGAN and ESRGAN.


Authors:
- Yu Zhang
- Alejandro Alvarez

## Description

The aim of this project is to implement x4 upscaling on low-resolution images from the dataset [DIV2K](https://data.vision.ee.ethz.ch/cvl/DIV2K/) using three different models:

- Convolutional Autoencoder
- Super-Resolution Generative Adversarial Network (SRGAN)
- Enhanced Super-Resolution Generative Adversarial Network (ESRGAN)

## Performance

The metrics used for performance evaluation were Peak Signal-to-Noise Ratio ([PSNR](https://en.wikipedia.org/wiki/Peak_signal-to-noise_ratio#:~:text=Peak%20signal%2Dto%2Dnoise%20ratio%20(PSNR)%20is%20an,the%20fidelity%20of%20its%20representation.)) and Structural Similarity Index Measure ([SSIM](https://en.wikipedia.org/wiki/Structural_similarity#:~:text=The%20structural%20similarity%20index%20measure,the%20similarity%20between%20two%20images.)).

## References

- Ledig, C., Theis, L., Huszár, F., Caballero, J., Cunningham, A., Acosta, A., ... & Shi, W. (2017). Photo-realistic single image super-resolution using a generative adversarial network. In Proceedings of the IEEE conference on computer vision and pattern recognition (pp. 4681-4690).

- Wang, X., Yu, K., Wu, S., Gu, J., Liu, Y., Dong, C., ... & Change Loy, C. (2018). Esrgan: Enhanced super-resolution generative adversarial networks. In Proceedings of the European Conference on Computer Vision (ECCV) Workshops (pp. 0-0).