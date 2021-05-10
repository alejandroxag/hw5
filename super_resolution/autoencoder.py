# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/autoencoder.ipynb (unless otherwise specified).

__all__ = ['PicturesDataset', 'plot_pictures', 'create_dataloaders', 'autoencoder', 'fit_and_log', 'parse_args', 'main',
           'create_test_loaders']

# Cell
import gc
gc.collect()
gc.get_count()

# Cell
# imports

import os
import glob
import time
import random
from tqdm import tqdm
import matplotlib.pyplot as plt

import torch
import numpy as np
import pytorch_ssim
import torch.nn as nn
from PIL import Image
from torchinfo import summary
from ignite.metrics import PSNR, SSIM
from torchvision import transforms
from torchvision.utils import save_image
from torch.optim import AdamW, lr_scheduler
import torchvision.transforms.functional as TF
from torch.utils.data import Dataset, DataLoader

# Cell
class PicturesDataset(Dataset):

    def __init__(self,
                 mode,
                 final_size,
                 normalize=False,
                 data_augmentation=None,
                 interpolation=TF.InterpolationMode.NEAREST,
                 in_memory=False,
                 verbose=False):

        s = time.time()

        # Assertions to avoid wrong inputs
        assert mode in ['train', 'val', 'test']
        assert (mode != 'train' and data_augmentation == None) or mode == 'train'
        if data_augmentation != None:
            for item in data_augmentation:
                assert item in ['crop', 'rotate', 'flip']

        # Directory setup
        data_dirs = {'train': './data/train',
                     'val': './data/val',
                     'test': './data/test'}

        self.data_dir = data_dirs[mode]
        self.mode = mode
        self.final_size = final_size
        self.data_augmentation = data_augmentation
        self.normalize = normalize
        self.verbose = verbose
        self.interpolation = interpolation
        self.in_memory=in_memory

        self.final_size_transf = transforms.Resize(size=[self.final_size, self.final_size],
                                                   interpolation=self.interpolation)

        self.pic_to_tensor = transforms.ToTensor()

        if mode != 'test':
            self.file_names_lr = sorted(glob.glob(f'{self.data_dir}/lr/*.png'))
            self.file_names_hr = sorted(glob.glob(f'{self.data_dir}/hr/*.png'))

            if in_memory:
                self.pics_lr = [self.pic_to_tensor(Image.open(f)) for f in self.file_names_lr]
                self.pics_hr = [self.pic_to_tensor(Image.open(f)) for f in self.file_names_hr]

        else:
            self.file_names_lr = []
            for folder in os.listdir(self.data_dir):
                self.file_names_lr += glob.glob(f'{self.data_dir}/{folder}/*.png')
            self.file_names_lr = sorted(self.file_names_lr)

            if in_memory:
                self.pics_lr = [self.pic_to_tensor(Image.open(f)) for f in self.file_names_lr]

        if verbose: print(f'class PicturesDataset Init time: {time.time() - s:0.2f}')


    def __len__(self):
        return len(self.file_names_lr)

    def __getitem__(self, idx):

        # Low resolution image (x)
        s = time.time()
        if self.in_memory: pic_lr = self.pics_lr[idx]
        else: pic_lr = transforms.ToTensor()(Image.open(self.file_names_lr[idx]))
        if pic_lr.shape[0] < 3: pic_lr = pic_lr.expand(3, pic_lr.shape[1], pic_lr.shape[2])
        if self.verbose: print(f'LR image reading time: {time.time() - s:0.2f}')

        # Flip dimensions to have height as longest dimension
        s = time.time()
        if pic_lr.shape[2] > pic_lr.shape[1]:
            pic_lr = pic_lr.transpose(1, 2)
        if self.verbose: print(f'LR Flipping time: {time.time() - s:0.2f}')

        # Normalization
        s = time.time()
        if self.normalize:
            pic_lr_mean = torch.mean(pic_lr.flatten(start_dim=1), dim=1)
            pic_lr_std = torch.std(pic_lr.flatten(start_dim=1), dim=1)
            pic_lr = TF.normalize(pic_lr, mean=pic_lr_mean, std=pic_lr_std)
        if self.verbose: print(f'LR Normalization time: {time.time() - s:0.2f}')

        # 4x rescaling
        s = time.time()
        pic_lr_h, pic_lr_w = pic_lr.shape[1], pic_lr.shape[2]
        pic_lr = TF.resize(pic_lr,
                           size=[4*pic_lr_h, 4*pic_lr_w],
                           interpolation=self.interpolation)
        if self.verbose: print(f'LR Rescaling time: {time.time() - s:0.2f}')

        if self.mode != 'test':

            # High resolution image (target, just for training and validation)
            s = time.time()
            if self.in_memory: pic_hr = self.pics_hr[idx]
            else: pic_hr = transforms.ToTensor()(Image.open(self.file_names_hr[idx]))
            if self.verbose: print(f'HR image reading time: {time.time() - s:0.2f}')

            # Flip dimensions to have height as longest dimension
            s = time.time()
            if pic_hr.shape[2] > pic_hr.shape[1]:
                pic_hr = pic_hr.transpose(1, 2)
            if self.verbose: print(f'HR Flipping time: {time.time() - s:0.2f}')

            # Normalization
            s = time.time()
            if self.normalize:
                pic_hr_mean = torch.mean(pic_hr.flatten(start_dim=1), dim=1)
                pic_hr_std = torch.std(pic_hr.flatten(start_dim=1), dim=1)
                pic_hr = TF.normalize(pic_hr, mean=pic_hr_mean, std=pic_hr_std)
            if self.verbose: print(f'HR Normalization time: {time.time() - s:0.2f}')

            # Data augmentation for x and target
            if self.data_augmentation != None:
                pic_lr, pic_hr = self.data_augmentation_transform(pic_lr, pic_hr)

            # Final resize
            s = time.time()

            pic_lr = self.final_size_transf(pic_lr)
            pic_hr = self.final_size_transf(pic_hr)
            if self.verbose: print(f'Final resize time: {time.time() - s:0.2f}')

            return pic_lr, pic_hr

        else:
            # Final resize
            s = time.time()
            pic_lr = self.final_size_transf(pic_lr)
            if self.verbose: print(f'Final resize time: {time.time() - s:0.2f}')

            pic_lr_size = {'heights': pic_lr_h, 'widths': pic_lr_w}
            if not self.normalize:
                pic_lr_mean = -1
                pic_lr_std = -1
            pic_lr_norm_params = {'means': pic_lr_mean, 'stds': pic_lr_std}

            return pic_lr, pic_lr_size, pic_lr_norm_params


    def data_augmentation_transform(self, pic_lr, pic_hr):

        assert pic_lr.shape == pic_hr.shape

        pic_h, pic_w = pic_lr.shape[1], pic_lr.shape[2]

        # Random rotation
        s = time.time()
        if 'rotate' in self.data_augmentation:
            angle = transforms.RandomRotation.get_params(degrees=[-45,45])

            pic_lr = TF.rotate(pic_lr, angle=angle)
            pic_hr = TF.rotate(pic_hr, angle=angle)
        if self.verbose: print(f'DA Rotation time: {time.time() - s:0.2f}')

        # Random flip
        s = time.time()
        if 'flip' in self.data_augmentation:

            # Random horizontal flipping
            if np.random.random() > 0.5:
                pic_lr = TF.hflip(pic_lr)
                pic_hr = TF.hflip(pic_hr)

            # Random vertical flipping
            if np.random.random() > 0.5:
                pic_lr = TF.vflip(pic_lr)
                pic_hr = TF.vflip(pic_hr)
        if self.verbose: print(f'DA Random Flipping time: {time.time() - s:0.2f}')

        # Random crop
        s = time.time()
        if 'crop' in self.data_augmentation:
            crop_factor = np.random.uniform(low=0.5, high=0.75)
            crop_h = np.round(crop_factor * pic_h, decimals=0).astype(int)
            crop_w = np.round(crop_factor * pic_w, decimals=0).astype(int)

            i, j, h, w = transforms.RandomCrop.get_params(pic_lr,
                                                          output_size=(crop_h, crop_w))

            pic_lr = TF.crop(img=pic_lr, top=i, left=j, height=h, width=w)
            pic_hr = TF.crop(img=pic_hr, top=i, left=j, height=h, width=w)
        if self.verbose: print(f'DA Cropping time: {time.time() - s:0.2f}')

        # Resize to original shape
        s = time.time()
        original_size = transforms.Resize(size=[pic_h, pic_w],
                                          interpolation=self.interpolation)
        pic_lr = original_size(pic_lr)
        pic_hr = original_size(pic_hr)
        if self.verbose: print(f'DA Resizing time: {time.time() - s:0.2f}')

        return pic_lr, pic_hr

# Cell
def plot_pictures(dataset, idx='random'):

    if idx == 'random': idx = np.random.randint(0, dataset.__len__() + 1)

    if dataset.mode != 'test':

        start = time.time()
        pic_lr, pic_hr = dataset.__getitem__(idx)
        if dataset.verbose: print(f'Total time: {time.time() - start:0.2f}\n')

        psnr = PSNR(data_range=1.0)
        psnr.update((pic_lr.unsqueeze(0), pic_hr.unsqueeze(0)))
        psnr_acc = psnr.compute()
        psnr.reset()

        ssim = SSIM(data_range=1.0)
        ssim.update((pic_lr.unsqueeze(0), pic_hr.unsqueeze(0)))
        ssim_acc = ssim.compute()
        ssim.reset()

        shape_lr = pic_lr.shape
        shape_hr = pic_hr.shape
        pic_lr = np.clip(pic_lr.permute(1,2,0).cpu().detach().numpy(), 0, 1)
        pic_hr = np.clip(pic_hr.permute(1,2,0).cpu().detach().numpy(), 0, 1)
        file_lr = dataset.file_names_lr[idx]
        file_hr = dataset.file_names_hr[idx]

        fig, axs = plt.subplots(1,2, figsize=(15,15))
        axs[0].imshow(pic_lr)
        title =  f'Low Resolution Image\nSet: {dataset.mode}\nNormalized: {dataset.normalize}\n'
        title += f'(shape: {shape_lr})\nPSNR: {psnr_acc:0.2f}\nSSIM: {ssim_acc:0.2f}\n{file_lr}'
        axs[0].set_title(title)
        axs[1].imshow(pic_hr)
        title =  f'High Resolution Image\nSet: {dataset.mode}\nNormalized: {dataset.normalize}\n'
        title += f'(shape: {shape_hr})\nPSNR: {psnr_acc:0.2f}\nSSIM: {ssim_acc:0.2f}\n{file_hr}'
        axs[1].set_title(title)
        plt.show()

    else:

        start = time.time()
        pic_lr, pic_lr_size, pic_lr_norm_params = dataset.__getitem__(idx)
        if dataset.verbose: print(f'Total time: {time.time() - start:0.2f}\n')

        shape_lr = pic_lr.shape
        file_lr = dataset.file_names_lr[idx]

        pic_lr_unnormalized = pic_lr * pic_lr_norm_params['stds'].unsqueeze(1).unsqueeze(2) + \
                              pic_lr_norm_params['means'].unsqueeze(1).unsqueeze(1)
        shape_lr_unnormalized = pic_lr_unnormalized.shape

        resize_pic = transforms.Resize(size=[pic_lr_size['heights'], pic_lr_size['widths']],
                                       interpolation=TF.InterpolationMode.BICUBIC)
        pic_lr_resized = resize_pic(pic_lr)
        shape_lr_resized = pic_lr_resized.shape

        pic_lr_resized_unnormalized = resize_pic(pic_lr_unnormalized)
        shape_lr_resized_unnormalized = pic_lr_resized_unnormalized.shape

        pic_lr = np.clip(pic_lr.permute(1,2,0).cpu().detach().numpy(), 0, 1)
        pic_lr_unnormalized = np.clip(pic_lr_unnormalized.permute(1,2,0).cpu().detach().numpy(), 0, 1)
        pic_lr_resized = np.clip(pic_lr_resized.permute(1,2,0).cpu().detach().numpy(), 0, 1)
        pic_lr_resized_unnormalized = np.clip(pic_lr_resized_unnormalized.permute(1,2,0).cpu().detach().numpy(), 0, 1)

        fig, axs = plt.subplots(2,2, figsize=(15,23))

        axs[0,0].imshow(pic_lr)
        axs[0,0].set_title(f'Low Resolution Image\nSet: {dataset.mode}\nNormalized: {True}\n(shape: {shape_lr})\n{file_lr}')

        axs[0,1].imshow(pic_lr_unnormalized)
        axs[0,1].set_title(f'Low Resolution Image\nSet: {dataset.mode}\nNormalized: {False}\n(shape: {shape_lr_unnormalized})\n{file_lr}')

        axs[1,0].imshow(pic_lr_resized)
        axs[1,0].set_title(f'Low Resolution Image\nOriginal size\nSet: {dataset.mode}\nNormalized: {True}\n(shape: {shape_lr_resized})\n{file_lr}')

        axs[1,1].imshow(pic_lr_resized_unnormalized)
        axs[1,1].set_title(f'Low Resolution Image\nOriginal size\nSet: {dataset.mode}\nNormalized: {False}\n(shape: {shape_lr_resized_unnormalized})\n{file_lr}')


        plt.show()

# Cell
def create_dataloaders(mc):

    NUM_WORKERS = os.cpu_count()

    train_dataset = PicturesDataset(mode='train',
                                    final_size=mc['final_size'],
                                    normalize=mc['normalize'],
                                    data_augmentation=mc['data_augmentation'],
                                    interpolation=mc['interpolation'],
                                    in_memory=mc['in_memory'],
                                    verbose=False)



    val_dataset =   PicturesDataset(mode='val',
                                    final_size=mc['final_size'],
                                    normalize=mc['normalize'],
                                    data_augmentation=None,
                                    interpolation=mc['interpolation'],
                                    in_memory=mc['in_memory'],
                                    verbose=False)

    test_dataset =  PicturesDataset(mode='test',
                                    final_size=mc['final_size'],
                                    normalize=mc['normalize'],
                                    data_augmentation=None,
                                    interpolation=mc['interpolation'],
                                    in_memory=False,
                                    verbose=False)

    display_str  = f'n_train: {len(train_dataset)} '
    display_str += f'n_val: {len(val_dataset)} '
    display_str += f'n_test: {len(test_dataset)} '
    print(display_str)

    train_loader = DataLoader(train_dataset,
                              shuffle=True,
                              batch_size=mc['batch_size'],
                              num_workers=NUM_WORKERS,
                              pin_memory=torch.cuda.is_available(),
                              drop_last=True)

    val_loader = DataLoader(val_dataset,
                            shuffle=False,
                            batch_size=mc['batch_size'],
                            num_workers=NUM_WORKERS,
                            pin_memory=torch.cuda.is_available(),
                            drop_last=True)

    test_loader = DataLoader(test_dataset,
                             shuffle=False,
                             batch_size=mc['batch_size'],
                             num_workers=NUM_WORKERS,
                             pin_memory=torch.cuda.is_available(),
                             drop_last=False)

    return train_loader, val_loader, test_loader

# Cell
class _autoencoder(nn.Module):

    def __init__(self,
                 h_channels):

        super(_autoencoder, self).__init__()

        h_channels = list(h_channels)
        self.channels_enc = [3]
        self.channels_enc += h_channels.copy()
        self.channels_dec = [self.channels_enc[-1]]
        self.channels_dec += h_channels[::-1].copy()

        # Input layer: (B, C=3, H, W)

        # Encoder
        encoder_layers = []

        for i in range(len(h_channels)):
            layer = [nn.Conv2d(in_channels=self.channels_enc[i],
                               out_channels=self.channels_enc[i+1],
                               kernel_size=3,
                               padding=1),
                     nn.BatchNorm2d(num_features=self.channels_enc[i+1]),
                     nn.ReLU(),
                     nn.MaxPool2d(kernel_size=2,
                                  stride=2)]
            encoder_layers += layer

        self.encoder_layers = nn.ModuleList(encoder_layers)

        # Decoder
        decoder_layers = []

        for i in range(len(self.channels_dec) - 1):
            layer = [nn.ConvTranspose2d(in_channels=self.channels_dec[i],
                                        out_channels=self.channels_dec[i+1],
                                        kernel_size=2,
                                        stride=2),
                     nn.BatchNorm2d(num_features=self.channels_dec[i+1]),
                     nn.ReLU()]
            decoder_layers += layer

        decoder_layers += [nn.Conv2d(in_channels=self.channels_dec[i+1],
                                    out_channels=self.channels_enc[0],
                                    kernel_size=3,
                                    padding=1),
                           nn.BatchNorm2d(num_features=self.channels_enc[0]),
                           nn.ReLU()]

        self.decoder_layers = nn.ModuleList(decoder_layers)


    def forward(self, x):

        # Encoding (Convolutional Blocks - Downsampling)
        output_shapes = []
        res_x = []

        for layer in self.encoder_layers:
            if isinstance(layer, torch.nn.modules.pooling.MaxPool2d):
                output_shapes.append(x.shape)

            x = layer(x)

            if isinstance(layer, torch.nn.modules.Conv2d): # skip connections
                res_x.append(x)

        output_shapes = output_shapes[::-1]
        res_x = res_x[::-1]

        # Decoding (Transpose Convolutional Blocks - Upsampling)
        for i, layer in enumerate(self.decoder_layers):
            if isinstance(layer, torch.nn.modules.conv.ConvTranspose2d):
                x = layer(x, output_size=output_shapes[i//3]) # if layer is ConvTranspose2D, then call it preserving output size from encoder
                x += res_x[i//3] # skip connections
            else:
                x = layer(x)

        return x


# Cell
class autoencoder(object):

    def __init__(self, params):

        super().__init__()
        self.params = params
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # Instantiate model

        #------------------------------------ Model & Optimizer ----------------------------------#

        self.model = _autoencoder(h_channels=params['h_channels'])

        print(summary(self.model,
                      input_size=(params['batch_size'],
                                  3,
                                  params['final_size'],
                                  params['final_size'])))

        self.model = nn.DataParallel(self.model).to(self.device)

        self.optimizer = AdamW(self.model.parameters(),
                               lr=params['initial_lr'],
                               weight_decay=params['weight_decay']) # Moved the optimizer outside
                                                                    # the fit method to also save
                                                                    # the optimizer state_dict.

        self.psnr = PSNR(data_range=1.0)
        self.ssim = SSIM(data_range=1.0)

    def fit(self, train_loader, val_loader):

        params = self.params

        self.time_stamp = time.time()

        torch.manual_seed(params['random_seed'])
        random.seed(params['random_seed'])
        np.random.seed(params['random_seed'])

        #------------------------------------- Optimization --------------------------------------#
        if params['criterion'] == 'ssim':
            cirterion = pytorch_ssim.SSIM()
        else:
            criterion = nn.MSELoss()


        scheduler = torch.optim.lr_scheduler.StepLR(self.optimizer,
                                                    step_size=params['adjust_lr_step'],
                                                    gamma=params['lr_decay'])

        scaler = torch.cuda.amp.GradScaler()

        #---------------------------------------- Logging -----------------------------------------#
        step = 0
        epoch = 0
        break_flag = False
        self.best_ssim = 0

        trajectories = {'step':  [],
                        'epoch':  [],
                        'train_loss': [],
                        'val_loss': [],
                        'train_psnr': [],
                        'val_psnr': [],
                        'train_ssim': [],
                        'val_ssim': []}

        print('\n'+'='*43+' Fitting  Autoencoder Model '+'='*43)

        while step <= params['iterations']:
            # Train
            epoch += 1

            self.model.train()

            start_epoch = time.time()

            for batch_idx, (x_lr, target_hr) in enumerate(train_loader):

                step+=1

                if break_flag: # weird epoch breaker
                    continue

                #--------------------------------- Forward and Backward ---------------------------------#
                x_lr = x_lr.to(self.device)
                target_hr = target_hr.to(self.device)

                self.optimizer.zero_grad()

                with torch.cuda.amp.autocast():

                    outputs = self.model(x_lr.float())


                    if params['criterion'] == 'ssim':
                        loss = -criterion(outputs, target_hr)
                    else:
                        loss = criterion(outputs, target_hr)

                    scaler.scale(loss).backward()
                    scaler.step(self.optimizer)
                    # Update optimizer learning rate
                    scaler.update()

                del x_lr
                del target_hr
                del outputs
                torch.cuda.empty_cache()

                scheduler.step()

            time_epoch = time.time() - start_epoch

                #----------------------------------- Evaluate metrics -----------------------------------#
            if (step % params['display_step']) == 0:

                start_eval = time.time()

                train_loss, train_psnr, train_ssim = \
                    self.evaluate_performance(train_loader, criterion)
                val_loss, val_psnr, val_ssim = \
                    self.evaluate_performance(val_loader, criterion)

                time_eval = time.time() - start_eval

                display_str = f'\nepoch: {epoch} (step: {step}) * '
                display_str += f'training time: {time_epoch:0.2f} '
                display_str += f'evaluation time: {time_eval:0.2f} * '
                display_str += f'train_loss: {train_loss:.4f} '
                display_str += f'val_loss: {val_loss:.4f} * '
                display_str += f'train_psnr: {train_psnr:0.2f} train_ssim: {train_ssim:0.2f} '
                display_str += f'val_psnr: {val_psnr:0.2f} val_ssim: {val_ssim:0.2f}'

                print(display_str)

                trajectories['train_loss'] += [train_loss]
                trajectories['val_loss']   += [val_loss]
                trajectories['train_psnr'] += [train_psnr]
                trajectories['val_psnr']   += [val_psnr]
                trajectories['train_ssim'] += [train_ssim]
                trajectories['val_ssim']   += [val_ssim]

                if val_ssim > self.best_ssim:

                    path = f"./checkpoint/{args.experiment_id}_{self.time_stamp}_ckpt.pth"
                    print(f'Saving to {path}')
                    self.best_ssim = val_ssim
                    self.save_weights(path=path,
                                      epoch=epoch,
                                      train_loss=train_loss,
                                      val_loss=val_loss,
                                      train_psnr=train_psnr,
                                      val_psnr=val_psnr,
                                      train_ssim=train_ssim,
                                      val_ssim=val_ssim)

            if step > params['iterations']:
                break_flag=True

        #---------------------------------------- Final Logs -----------------------------------------#
        print('\n'+'='*43+' Finished Train '+'='*43)
        self.train_loss = trajectories['train_loss'][-1]
        self.val_loss = trajectories['val_loss'][-1]
        self.train_psnr = trajectories['train_psnr'][-1]
        self.val_psnr = trajectories['val_psnr'][-1]
        self.train_ssim = trajectories['train_ssim'][-1]
        self.val_ssim = trajectories['val_ssim'][-1]
        self.trajectories = trajectories


    def evaluate_performance(self, loader, criterion):

        self.model.eval()
        params = self.params
        running_loss = 0

        with torch.no_grad():
            for batch_idx, (x_lr, target_hr) in enumerate(loader):

                x_lr = x_lr.to(self.device)
                target_hr = target_hr.to(self.device)

                outputs = self.model(x_lr.float())
                loss = criterion(outputs, target_hr)

                running_loss += loss.item()
                self.psnr.update((outputs, target_hr))
                self.ssim.update((outputs, target_hr))

                # Clean memory
                del x_lr
                del target_hr
                del outputs
                torch.cuda.empty_cache()

        running_loss /= len(loader) * params['batch_size']
        psnr_score = self.psnr.compute()
        ssim_score = self.ssim.compute()

        self.psnr.reset()
        self.ssim.reset()

        self.model.train()

        return running_loss, psnr_score, ssim_score

    def predict_labels(self, loader):

        self.model.eval()

        files = [f.split('/')[-1] for f in loader.dataset.file_names_lr]

        with torch.no_grad():
            for batch_idx, (x_lr, x_lr_size, x_lr_norm_params) in tqdm(enumerate(loader)):

                x_lr = x_lr.to(self.device)
                x_lr_size['heights'] = 4 * x_lr_size['heights'].to(self.device)
                x_lr_size['widths'] = 4 * x_lr_size['widths'].to(self.device)

                x_lr_norm_params['stds'] = x_lr_norm_params['stds'].to(self.device)
                x_lr_norm_params['means'] = x_lr_norm_params['means'].to(self.device)

                outputs = self.model(x_lr.float())

                output_hr = TF.resize(outputs[0],
                                      size=[x_lr_size['heights'][0].item(),
                                            x_lr_size['widths'][0].item()],
                                      interpolation=TF.InterpolationMode.BICUBIC)

                pic_set = loader.dataset.data_dir.split('/')[-1]

                results_path = f'./results/{self.params["experiment_id"]}/test/{pic_set}'

                if not os.path.exists(results_path):
                    os.makedirs(results_path)

                save_image(output_hr, f'{results_path}/{files[batch_idx]}')

                # Clean memory
                del x_lr
                del x_lr_size
                del x_lr_norm_params
                del outputs
                torch.cuda.empty_cache()

    def save_weights(self,
                     path,
                     epoch,
                     train_loss,
                     val_loss,
                     train_psnr,
                     val_psnr,
                     train_ssim,
                     val_ssim):

        if not os.path.exists('./checkpoint/'):
            os.makedirs('./checkpoint/')

        torch.save({'epoch': epoch,
                    'model_state_dict': self.model.state_dict(),
                    'optimizer_state_dict': self.optimizer.state_dict(),
                    'train_loss': train_loss,
                    'val_loss': val_loss,
                    'train_psnr': train_psnr,
                    'val_psnr': val_psnr,
                    'train_ssim': train_ssim,
                    'val_ssim': val_ssim},
                    path)

    def load_weights(self, path):

        checkpoint = torch.load(path, map_location=torch.device(self.device))

        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.model.eval()

# Cell
def fit_and_log(mc, verbose, trials=None):

    start_time = time.time()

    train_loader, val_loader, _ = create_dataloaders(mc)

    print('='*50)
    print(pd.Series(mc))
    print('='*50+'\n')

    model = autoencoder(params=mc)

    model.fit(train_loader=train_loader,
              val_loader=val_loader)

    print(f'Model fit time: {time.time() - start_time}')

    results = {#----------------- Hyperopt -----------------#
               'loss': model.val_loss,
               'status': STATUS_OK,
               'mc': mc,
               'path': mc['path'],
               #------------------- Logs -------------------#
               'train_loss': model.train_loss,
               'val_loss': model.val_loss,
               'train_psnr': model.train_psnr,
               'val_psnr': model.val_psnr,
               'train_ssim': model.train_ssim,
               'val_ssim': model.val_ssim,
               'run_time': time.time()-start_time,
               'trajectories': model.trajectories}

    return results

# Cell
from hyperopt import Trials, fmin, hp, tpe
from hyperopt.pyll.base import scope
from functools import partial
import argparse
import pickle
import pandas as pd
from hyperopt import STATUS_OK

# Cell
def parse_args():
    desc = "Autoencoder for image super-resolution"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('--n_epochs', required=True, type=int, help='number of epochs')
    parser.add_argument('--batch_size', required=True, type=int, help='Batch size')
    parser.add_argument('--n_eval_steps', required=True, type=int, help='Number of display and eval steps')
    parser.add_argument('--hyperopt_max_evals', required=True, type=int, help='Hyperopt evaluations')
    parser.add_argument('--experiment_id', required=True, type=str, help='string to identify experiment')
    return parser.parse_args()

# Cell
def main(args, max_evals):

    model_path = f"./checkpoint/{args.experiment_id}_ckpt.pth"
    trials_path = f"./results/{args.experiment_id}_trials.p"

    iterations = (800 // args.batch_size) * args.n_epochs

    display_step = iterations // args.n_eval_steps

    space = {'experiment_id': hp.choice(label='experiment_id', options=[args.experiment_id]),
             #------------------------------------- Architecture -------------------------------------#
#              'h_channels': hp.choice(label='h_channels', options=[[8, 16, 32, 64, 128, 256]]),
             'h_channels': hp.choice(label='h_channels', options=[[8, 16, 32, 64]]),
             'final_size': hp.choice(label='final_size', options=[2040]),
             'normalize': hp.choice(label='normalize', options=[False]),
             'data_augmentation': hp.choice(label='data_augmentation', options=[['crop', 'rotate', 'flip']]),
             'interpolation': hp.choice(label='interpolation', options=[TF.InterpolationMode.BILINEAR]),
             'in_memory': hp.choice(label='in_memory', options=[False]),
             'criterion': hp.choice(label='criterion', options=['mse']),
             #------------------------------ Optimization Regularization -----------------------------#
             'batch_size': hp.choice(label='batch_size', options=[args.batch_size]),
#              'initial_lr': hp.loguniform(label='initial_lr', low=np.log(5e-3), high=np.log(1e-2)),
             'initial_lr': scope.float(hp.choice(label='initial_lr', options=[0.009364])),
             'weight_decay': scope.float(hp.choice(label='weight_decay', options=[1e-6])),
             'adjust_lr_step': hp.choice(label='adjust_lr_step', options=[iterations//3]),
             'lr_decay': scope.float(hp.choice(label='lr_decay', options=[0.1])),
             'iterations': hp.choice(label='iterations', options=[iterations]),
             'n_epochs': hp.choice(label='n_epochs', options=[args.n_epochs]),
             'display_step': hp.choice(label='display_step', options=[display_step]),
             #--------------------------------------   Others   --------------------------------------#
             'path': hp.choice(label='path', options=[model_path]),
             'trials_path': hp.choice(label='trials_path', options=[trials_path]),
             'random_seed': hp.choice(label='random_seed', options=[7])}


    trials = Trials()
    fmin_objective = partial(fit_and_log, trials=trials, verbose=True)
    best_model = fmin(fmin_objective, space=space, algo=tpe.suggest, max_evals=max_evals, trials=trials)

    with open(trials_path, "wb") as f:
        pickle.dump(trials, f)

# Cell
def create_test_loaders(folder, mc):

    NUM_WORKERS = os.cpu_count()

    test_dataset =  PicturesDatasetTest(folder,
                                        interpolation=mc['interpolation'])

    display_str = f'n_test: {len(test_dataset)} '
    print(display_str)

    test_loader = DataLoader(test_dataset,
                             shuffle=False,
                             batch_size=mc['batch_size'],
                             num_workers=NUM_WORKERS,
                             pin_memory=torch.cuda.is_available(),
                             drop_last=False)

    return test_loader