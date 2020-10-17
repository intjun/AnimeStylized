import os
import sys
sys.path.insert(0, os.getcwd())
import pytorch_lightning as pl
from networks.gan import SpectNormDiscriminator, UnetGenerator, AnimeDiscriminator
from networks.pretrainnet import VGGPreTrained
from datasets.whiteboxgan import WhiteBoxGanDataModule, denormalize
from losses.gan_loss import LSGanLoss
from losses.function import variation_loss, rgb2yuv
from typing import Dict, List, Tuple
import torch
import torch.nn as nn
import torch.nn.functional as nf
import torch.functional as F
import torchvision.transforms.functional as tf
from scripts.common import run_train, log_images
from scripts.animegan import AnimeGAN


class AnimeGANv2(AnimeGAN):

  def __init__(self, tv_weight: float = 1., **kwargs):
    super().__init__(tv_weight=tv_weight, **kwargs)

  def inner_training_step(self, batch: Dict[str, torch.Tensor]):
    input_photo = batch['real_data']
    input_cartoon = batch['anime_data']
    anime_gray_data = batch['anime_gray_data']
    anime_smooth_gray_data = batch['anime_smooth_gray_data']

    generated = self.generator(input_photo)

    anime_logit = self.discriminator(input_cartoon)
    anime_gray_logit = self.discriminator(anime_gray_data)
    generated_logit = self.discriminator(generated)
    smooth_logit = self.discriminator(anime_smooth_gray_data)

    # 利用灰度化的图像学习style特征
    c_loss, s_loss = self.con_sty_loss(input_photo, anime_gray_data, generated)
    c_loss = self.hparams.con_weight * c_loss
    s_loss = self.hparams.sty_weight * s_loss
    tv_loss = self.hparams.tv_weight * variation_loss(generated)
    col_loss = self.color_loss(input_photo, generated) * self.hparams.color_weight
    g_loss = (self.hparams.g_adv_weight * self.generator_loss(generated_logit))
    (d_real_loss, d_gray_loss, d_fake_loss, d_real_blur_loss) = self.discriminator_loss(
        anime_logit, anime_gray_logit,
        generated_logit, smooth_logit)
    d_loss_total = (self.hparams.d_adv_weight * (d_real_loss +
                                                 d_fake_loss +
                                                 d_gray_loss +
                                                 d_real_blur_loss))
    g_loss_total = c_loss + s_loss + col_loss + g_loss + tv_loss
    self.log_dict({
        'dis/d_loss': d_loss_total,
        'dis/d_real_loss': d_real_loss,
        'dis/d_fake_loss': d_fake_loss,
        'dis/d_gray_loss': d_gray_loss,
        'dis/d_real_blur_loss': d_real_blur_loss,
        'gen/g_loss': g_loss,
        'gen/c_loss': c_loss,
        'gen/s_loss': s_loss,
        'gen/col_loss': col_loss,
        'gen/tv_loss': tv_loss})
    return d_loss_total, g_loss_total

  def training_step(self, batch: Dict[str, torch.Tensor], batch_idx, optimizer_idx):
    if optimizer_idx == 0:
      d_loss_total, _ = self.inner_training_step(batch)
      return d_loss_total

    elif optimizer_idx == 1:  # train generator
      _, g_loss_total = self.inner_training_step(batch)
      return g_loss_total


if __name__ == "__main__":
  run_train(AnimeGANv2, WhiteBoxGanDataModule)