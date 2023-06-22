import os

import matplotlib.pyplot as plt
import torch
import torch.utils.data
from dataset import (ImageCaptionDataset, denormalize, get_data_loader,
                     preprocessing_transforms)
from vocab import Vocab
from model import Decoder, Encoder
from config import *

from nltk.translate import bleu_score

def generate_caption(image: torch.Tensor, image_encoder: Encoder, emb_layer: torch.nn.Embedding, image_decoder: Decoder, vocab: Vocab, device: torch.device) -> list[str]:
    """ Generate caption of a single image of size (3, 224, 224)

    Returns:
        list[str]: caption for given image
    """
    
    image = image.to(device)
    # image: (3, 224, 224)
    image = image.unsqueeze(0) 
    # image: (1, 3, 224, 224)

    features = image_encoder.forward(image)
    # features: (1, IMAGE_EMB_DIM)
    features = features.to(device)
    features = features.unsqueeze(0) 
    # features: (1, 1, IMAGE_EMB_DIM)
    
    hidden= image_decoder.hidden_state_0 
    cell =image_decoder.cell_state_0 
    # hidden, cell : (NUM_LAYER, 1, HIDDEN_DIM)
    
    sentence = []
    
    # start with '<sos>' as first word
    previous_word = vocab.index2word[vocab.SOS]

    MAX_LENGTH = 20
    
    for i in range(MAX_LENGTH):
        
        input_word_id = vocab.word_to_index(previous_word)
        input_word_tensor = torch.tensor([input_word_id]).unsqueeze(0) 
        # input_word_tensor : (1, 1)
        
        input_word_tensor = input_word_tensor.to(device)
        lstm_input = emb_layer.forward(input_word_tensor)
        # lstm_input : (1, 1, WORD_EMB_DIM)
        
        next_word_pred, (hidden, cell) = image_decoder.forward(lstm_input, features, hidden, cell)
        # next_word_pred : (1, 1, VOCAB_SIZE)
        
        next_word_pred = next_word_pred[0,0,:] 
        # next_word_pred : (VOCAB_SIZE)
        
        next_word_pred = torch.argmax(next_word_pred)
        next_word_pred = vocab.index_to_word(int(next_word_pred.item()))
        sentence.append(next_word_pred)
        previous_word = next_word_pred
        
        # stop if we predict '<eos>'
        if next_word_pred == vocab.index2word[vocab.EOS]:
            break
        
    return sentence
        
        

if __name__ == '__main__':
    
    config = Config()
    
    print('Loading vocabulary...')
    vocab = Vocab()
    vocab.load_vocab(config.VOCAB_FILE)

    print('Loading data...')
    val_data = ImageCaptionDataset('val_list.txt', vocab, 'images', transform=preprocessing_transforms())
     
    print('Creating model...')
    image_encoder = Encoder(image_emb_dim = config.IMAGE_EMB_DIM, 
                            device= config.DEVICE)
    emb_layer = torch.nn.Embedding(num_embeddings = config.VOCAB_SIZE, 
                                   embedding_dim = config.WORD_EMB_DIM,
                                   padding_idx = vocab.PADDING_INDEX)
    image_decoder = Decoder(image_emb_dim = config.IMAGE_EMB_DIM,
                            word_emb_dim = config.WORD_EMB_DIM,
                            hidden_dim = config.HIDDEN_DIM,
                            num_layers = config.NUM_LAYER,
                            vocab_size = config.VOCAB_SIZE,
                            device = config.DEVICE)

    emb_layer.eval()
    image_encoder.eval()
    image_decoder.eval()

    LOAD_WEIGHTS = True
    if LOAD_WEIGHTS:
        print("Loading pretrained weights...")
        emb_layer.load_state_dict(torch.load(config.EMBEDDING_WEIGHT_FILE))
        image_encoder.load_state_dict(torch.load(config.ENCODER_WEIGHT_FILE))
        image_decoder.load_state_dict(torch.load(config.DECODER_WEIGHT_FILE))
        
    
    emb_layer = emb_layer.to(config.DEVICE)
    image_encoder = image_encoder.to(config.DEVICE)
    image_decoder = image_decoder.to(config.DEVICE)
    
    
    print('Visualizing results...')
    val_loader = get_data_loader(val_data, batch_size=32, pad_index=vocab.PADDING_INDEX)
    x, y = next(iter(val_loader)) 
    
    for image, caption in zip(x, y):
        
        im = image.to(config.DEVICE)
        image = denormalize(image)
        
        sentence = generate_caption(im, image_encoder,emb_layer,image_decoder, vocab, device=config.DEVICE)
        sentence = [word for word in sentence if word not in ['<pad>', '<sos>', '<eos>']]
        
        caption = [vocab.index_to_word(int(word_id)) for word_id in caption]
        caption = [word for word in caption if word not in ['<pad>', '<sos>', '<eos>']]
        
        weights = [
         (1., 0, 0, 0),
         (1./2., 1./2., 0, 0)
        ]
        
        bleu = bleu_score.sentence_bleu([sentence], caption, weights)
        
        sentence = ' '.join(str(word) for word in sentence)
        caption = ' '.join(str(word) for word in caption)
        
        text = 'Real: %s            \n \
                Generated: %s       \n \
                Bleu-1 score: %.2f  \n \
                Bleu-2 score: %.2f' % (caption, sentence, bleu[0], bleu[1])
        
        plt.imshow(image)
        plt.title(text)
        plt.show()
        plt.pause(1)  
