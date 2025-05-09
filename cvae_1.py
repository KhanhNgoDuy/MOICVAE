import argparse
from torch.nn import init
import torch
from torch import nn
from torch import optim
from torch.nn import functional
from torch.utils.data import DataLoader
import numpy as np
from sklearn.model_selection import KFold
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
from sklearn.metrics import average_precision_score,accuracy_score,f1_score,recall_score,precision_score
from torch.autograd import Variable
import matplotlib.pyplot as plt
# from layer import Encoder, Decoder, build_mlp, DeterministicWarmup
from itertools import repeat
# from loss2 import elbo_SCALE,elbo
from sklearn.mixture import GaussianMixture
import time
import math
from tqdm import trange
from pathlib import Path
import os
import pandas as pd

#重参数化
def regularization(mu, logvar):
    return -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp())
#损失
def Guassian_loss(recon_x, x):
    weights = x * args.alpha + (1 - x)
    loss = x - recon_x
    loss = torch.sum(weights * loss * loss)
    return loss

#交叉熵损失
def BCE_loss(recon_x, x):
    eps = 1e-8
    loss = -torch.sum(args.alpha * torch.log(recon_x + eps) * x + torch.log(1 - recon_x + eps) * (1 - x))
    return loss

###@@@@@@wd@@@@@@@
def train(epoch):
    model.train()
    loss_value = 0
    ### Full dataset = (# drugs, # samples)
    ### Batch = (N, # samples) --> bug??
    for batch_idx, data in enumerate(train_loader):
        
        data = data.to(args.device)
        data = Variable(data)
        data_v, data_i = torch.chunk(data,2,dim=1)
        optimizer.zero_grad()
        recon_batch, mu, logvar = model(data_v)#计算所有的
        one_index = data_i.nonzero()[:,0]*data_i.size(1) + data_i.nonzero()[:,1]#打散后的索引
        # print(data_i[0])
        # print(recon_batch.flatten().index_select(0,torch.LongTensor(one_index)).shape)
        # print(data_v.flatten().index_select(0,torch.LongTensor(one_index)).shape)
        exit()
        loss = loss_function(recon_batch.flatten().index_select(0,torch.LongTensor(one_index)), data_v.flatten().index_select(0,torch.LongTensor(one_index))) + regularization(mu, logvar) * args.beta
        loss.backward()
        loss_value += loss.item()
        optimizer.step()
        if args.log != 0 and batch_idx % args.log == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, batch_idx * len(data), len(train_loader.dataset),
                       100. * batch_idx / len(train_loader),
                       loss.item() / len(data)))

    print('====> Epoch: {} Average loss: {:.4f}'.format(
        epoch, loss_value / train_loader.dataset.chunk(2,dim=1)[1].nonzero().size(0)))
    return loss_value / train_loader.dataset.chunk(2,dim=1)[1].nonzero().size(0)


def eval(test_loader, model, loss=None):    
    with torch.no_grad():
        model.eval()
        preds = []

        ### batch_size = 1
        for batch_idx, data in enumerate(test_loader):
            data = data.to(args.device)
            data_v, data_i = torch.chunk(data, 2, dim=1)
            recon_batch, mu, logvar = model(data_v)
            preds.append(recon_batch.squeeze(0))
        
        preds = torch.stack(preds, dim=0)
        return preds


# Implementation of Variaitonal Autoencoder
class VAE(nn.Module):
    # Define the initialization function，which defines the basic structure of the neural network
    def __init__(self, args):
        super(VAE, self).__init__()
        self.l = len(args.layer)
        self.L = args.L
        self.device = args.device
        self.inet = nn.ModuleList()
        darray = [args.d] + args.layer
        for i in range(self.l - 1):
            self.inet.append(nn.Linear(darray[i], darray[i + 1]))
        self.mu = nn.Linear(darray[self.l - 1], darray[self.l])
        self.sigma = nn.Linear(darray[self.l - 1], darray[self.l])
        self.gnet = nn.ModuleList()
        for i in range(self.l):
            self.gnet.append(nn.Linear(darray[self.l - i], darray[self.l - i - 1]))
    
    def encode(self, x):
        h = x
        for i in range(self.l - 1):
            #h = functional.relu(self.inet[i](h))
            h = functional.relu(functional.dropout(self.inet[i](h), p=0.0, training=True))
        return self.mu(h), self.sigma(h)

    def decode(self, z):
        h = z
        for i in range(self.l - 1):
            #h = functional.relu(self.gnet[i](h))
            h = functional.relu(functional.dropout(self.gnet[i](h), p=0.0, training=True))
        return torch.sigmoid(self.gnet[self.l - 1](h))

    def reparameterize(self, mu, logvar):
        if self.training:
            std = torch.exp(0.5 * logvar)
            eps = torch.randn([self.L] + list(std.shape)).to(self.device)
            return eps.mul(std).add_(mu)
        else:
            return mu
#        return torch.randn_like(mu).mul_(torch.exp(0.5 * logvar)).add_(mu)

#     def reparameterize(self, mu, logvar):
#         epsilon = torch.randn(mu.size(), requires_grad=False, device=mu.device)
#         std = logvar.mul(0.5).exp_()
#         std = torch.clamp(logvar.mul(0.5).exp_(), -5, 5)
#         z = mu.addcmul(std, epsilon)
#         return z
    # Define the forward propagation function for the neural network.
    # Once defined, the backward propagation function will be autogeneration（autograd）
    def forward(self, x):
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        return self.decode(z), mu, logvar

        
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Variational Auto Encoder')
    parser.add_argument('--batch', type=int, default=10, help='input batch size for training (default: 100)')
    parser.add_argument('-m', '--maxiter', type=int, default=10, help='number of epochs to train (default: 10)')
    parser.add_argument('--gpu', action='store_true', default=False, help='enables CUDA training')
    parser.add_argument('--seed', type=int, default=2, help='random seed (default: 1)')
    parser.add_argument('--log', type=int, default=1, metavar='N',
                        help='how many batches to wait before logging training status')
    parser.add_argument('--dir', help='dataset directory', default='/Users/deepDR/dataset')
    parser.add_argument('--layer', nargs='+', help='number of neurals in each layer', type=int, default=[20])
    parser.add_argument('-L', type=int, default=1, help='number of samples')
    # parser.add_argument('-N', help='number of recommended items', type=int, default=20)
    parser.add_argument('--learn_rate', help='learning rate', type=float, default=0.001)
    parser.add_argument('-a', '--alpha', help='parameter alpha', type=float, default=1)
    parser.add_argument('-b', '--beta', help='parameter beta', type=float, default=1)
    parser.add_argument('--rating', help='feed input as rating', action='store_true')
    parser.add_argument('--save', help='save model', action='store_true')
    parser.add_argument('--load', help='load model, 1 for fvae and 2 for cvae', type=int, default=0)
    parser.add_argument('--eval', help='flag for testing & saving predictions to a file', action='store_true')
    # parser.add_argument('--eval', help='flag for testing & saving predictions to a file', type=int, default=0)

    args = parser.parse_args()
    torch.manual_seed(args.seed)
    # whether to ran with cuda
    args.device = torch.device("cuda" if args.gpu and torch.cuda.is_available() else "cpu")
    
    print('dataset directory: ' + args.dir)
    directory = args.dir     #数据目录

    if not args.eval:
        if args.rating:  # feed in with rating
            # ### original data
            # # folder_GDSC='./data/Datasets/CCLE_dataset/dataset/'
            # path = os.path.join(directory, 'matrix of 0 and 1.txt')
            # print('train data path: ' + path)
            # R = np.loadtxt(path)#cellline*drug
            # Rtensor = R.transpose()#drug*cellline

            ### our data
            path = os.path.join(directory, 'binary_matrix.csv')
            df = pd.read_csv(path)  # Replace with your file
            data_only = df.iloc[:, 1:]
            data_array = data_only.to_numpy(dtype=float)
            R = data_array
            Rtensor = R.transpose()

            whole_positive_index = []
            whole_negative_index = []

            ### Thằng thứ j đang có/ko có response với drug thứ i
            for i in range(np.shape(Rtensor)[0]):
                for j in range(np.shape(Rtensor)[1]):
                    if int(Rtensor[i][j]) == 1:
                        whole_positive_index.append([i, j])
                    elif int(Rtensor[i][j]) == 0:
                        whole_negative_index.append([i, j])
            negative_sample_index = np.random.choice(np.arange(len(whole_negative_index)),
                                                    size=1 * len(whole_positive_index), replace=False)
            # whole_negative_index=np.array(whole_negative_index) 
            ### khanh: Rtensor.shape[0] * Rtensor.shape[1] = whole_positive_index + whole_negative_index

            data_set = np.zeros((len(whole_negative_index) + len(whole_positive_index), 3), dtype=int)#N*3的指示矩阵
            count = 0
            for i in whole_positive_index:
                data_set[count][0] = i[0]   ### drug
                data_set[count][1] = i[1]   ### sample
                data_set[count][2] = 1      ### positive response
                count += 1
            for i in whole_negative_index:#negative_sample_index:
                data_set[count][0] = i[0]   ### drug
                data_set[count][1] = i[1]   ### sample
                data_set[count][2] = 0      ### negative response
                count += 1
            test_auc_fold = []
            test_aupr_fold = []
            test_accu_fold = []
            test_f1_fold = []
            test_preci_fold = []
            test_recall_fold = [] 
            
            rs = np.random.randint(0, 1000, 1)[0]
            kf = StratifiedKFold( n_splits=10, shuffle=True, random_state=23)

            for train_index, test_index in kf.split(data_set[:, range(2)],data_set[:, 2]):#索引值，label
                DTItrain, DTItest = data_set[train_index], data_set[test_index]#列表形式
                Xtrain = np.zeros((np.shape(Rtensor)[0], np.shape(Rtensor)[1]))
                data_train_index = np.zeros((np.shape(Rtensor)[0], np.shape(Rtensor)[1]))

                Xtest = np.zeros((np.shape(Rtensor)[0], np.shape(Rtensor)[1]))
                for ele in DTItrain:
                    Xtrain[ele[0], ele[1]] = ele[2]#矩阵形式
                    data_train_index[ele[0],ele[1]] = 1
                for ele in DTItest:
                    Xtest[ele[0], ele[1]] = ele[2]#矩阵形式
                    
                Rtensor = torch.from_numpy(Xtrain.astype('float32')).to(args.device)#矩阵形式
                data_train_index = torch.from_numpy(data_train_index.astype('float32')).to(args.device)
                Rtesttensor = torch.from_numpy(Xtest.astype('float32')).to(args.device)#矩阵形式
                Rtensor2 = torch.cat([Rtensor,data_train_index],axis=1)
                print(Rtensor.shape)
                print(Rtesttensor.shape)
                print(data_train_index.shape)

                args.d = Rtensor.shape[1]#特征维度
                # train_loader = DataLoader(Rtensor2, args.batch, shuffle=True)
                print("[KHANH] DEBUGGING")
                print(Rtensor[0])
                print(Rtensor.shape)
                train_loader = DataLoader(Rtensor2, 1, shuffle=False)
                loss_function = BCE_loss
                model = VAE(args).to(args.device)
                if args.load > 0:
                    name = 'cvae' if args.load == 2 else 'fvae'
                    path = 'test_models/' + name
                    for l in args.layer:
                        path += '_' + str(l)
                    print('load model from path: ' + path)
                    model.load_state_dict(torch.load(f"{path}.pth"))

                optimizer = optim.Adam(model.parameters(), lr=args.learn_rate)
    ##############@@@wd##############
                loss_list = []
                for epoch in range(1, args.maxiter + 1):
                    loss = train(epoch)
                    loss_list.append(loss)

                model.eval()
                score, _, _ = model(Rtensor)
                Zscore = score.detach().numpy() #打分
                pred_list = []
                ground_truth = []
                pred_list_label = []
                for ele in DTItrain:
                    pred_list.append(Zscore[ele[0], ele[1]])
                    pred_list_label.append(1 if Zscore[ele[0], ele[1]]>0.5 else 0)
                    ground_truth.append(ele[2])
                train_auc = roc_auc_score(ground_truth, pred_list)
                train_aupr = average_precision_score(ground_truth, pred_list)
                train_accu, train_preci, train_recall = accuracy_score(ground_truth, pred_list_label), precision_score(ground_truth, pred_list_label), recall_score(ground_truth, pred_list_label)
                train_f1  = f1_score(ground_truth,pred_list_label)           
                print('train: auc aupr accu preci recall f1', train_auc, train_aupr,train_accu, train_preci, train_recall, train_f1)
                pred_list = []
                ground_truth = []
                pred_list_label = []
                for ele in DTItest: #预测的元素
                    pred_list.append(Zscore[ele[0], ele[1]])
                    pred_list_label.append(1 if Zscore[ele[0], ele[1]]>0.5 else 0)
                    ground_truth.append(ele[2])
                test_auc = roc_auc_score(ground_truth, pred_list)
                test_aupr = average_precision_score(ground_truth, pred_list)
                test_accu, test_preci, test_recall = accuracy_score(ground_truth, pred_list_label), precision_score(ground_truth, pred_list_label), recall_score(ground_truth, pred_list_label)
                test_f1 = f1_score(ground_truth, pred_list_label)
                print('test auc aupr accu preci recall f1', test_auc, test_aupr, test_accu, test_preci, test_recall, test_f1)
                test_auc_fold.append(test_auc)
                test_aupr_fold.append(test_aupr)
                test_accu_fold.append(test_accu), test_preci_fold.append(test_preci), test_recall_fold.append(test_recall) 
                test_f1_fold.append(test_f1)
                # model.train()
            avg_auc = np.mean(test_auc_fold)
            avg_pr = np.mean(test_aupr_fold)
            avg_accu, avg_preci, avg_recall = np.mean(test_accu_fold), np.mean(test_preci_fold), np.mean(test_recall_fold)
            avg_f1 = np.mean(test_f1_fold)
            print('mean auc aupr accu preci recall f1', avg_auc, avg_pr, avg_accu, avg_preci, avg_recall, avg_f1)

            
        else:  # feed in with side information
            ### original data
            # path = 'celllinemdaFeatures.txt'
            # path = 'celllinemdaFeatures3.txt'
            # print('feature data path: ' + path)
            # fea = np.loadtxt(path)
            # X = fea.transpose()

            ### our data
            path = 'patient_correlation_matrix.csv'
            df = pd.read_csv(path)  # Replace with your file
            data_only = df.iloc[:, 1:]
            data_array = data_only.to_numpy(dtype=float)
            X = data_array

            args.d = X.shape[1] #特征个数
            # X = normalize(X, axis=1)
            X_index = torch.ones(X.shape)
            X = torch.from_numpy(X.astype('float32')).to(args.device)
            X = torch.cat([X,X_index],axis=1)
            train_loader = DataLoader(X, args.batch, shuffle=True)
            loss_function = Guassian_loss
    ##################################################################
            model = VAE(args).to(args.device)
            if args.load > 0:
                name = 'cvae' if args.load == 2 else 'fvae'
                path = 'test_models/' + name
                for l in args.layer:
                    path += '_' + str(l)
                print('load model from path: ' + path)
                model.load_state_dict(torch.load(path))

            optimizer = optim.Adam(model.parameters(), lr=args.learn_rate)
    ###@@@@@@@@@@@@@@@wd####################
            for epoch in range(1, 300 + 1):
                train(epoch)

        if args.save:
            name = 'cvae' if args.rating else 'fvae'
            path = Path('test_models')
            Path(path).mkdir(parents=True, exist_ok=True)

            for l in args.layer:
                name += '_' + str(l)
            model.cpu()
            torch.save(model.state_dict(), path / f"{name}.pth")
    else:
        print("EVALUATING")

        ### our data
        path = os.path.join(directory, 'binary_matrix.csv')
        # df = pd.read_csv(path)  # Replace with your file
        # data_only = df.iloc[:, 1:]
        # data_array = data_only.to_numpy(dtype=float)
        
        df = pd.read_csv(path, index_col=0)
        data_array = df.values

        R = data_array
        Rtensor = R.transpose()

        whole_positive_index = []
        whole_negative_index = []
        for i in range(np.shape(Rtensor)[0]):
            for j in range(np.shape(Rtensor)[1]):
                if int(Rtensor[i][j]) == 1:
                    whole_positive_index.append([i, j])
                elif int(Rtensor[i][j]) == 0:
                    whole_negative_index.append([i, j])
        negative_sample_index = np.random.choice(np.arange(len(whole_negative_index)),
                                                size=1 * len(whole_positive_index), replace=False)
        
        data_set = np.zeros((len(whole_negative_index) + len(whole_positive_index), 3), dtype=int)#N*3的指示矩阵
        count = 0
        for i in whole_positive_index:
            data_set[count][0] = i[0]#行列值
            data_set[count][1] = i[1]
            data_set[count][2] = 1
            count += 1
        for i in whole_negative_index:#negative_sample_index:
            data_set[count][0] = i[0] #whole_negative_index[i][0]
            data_set[count][1] = i[1] #whole_negative_index[i][1]
            data_set[count][2] = 0
            count += 1


        # Build full dataset
        Xtrain = np.zeros((np.shape(Rtensor)[0], np.shape(Rtensor)[1]))
        data_train_index = np.zeros_like(Xtrain)

        for ele in data_set:
            Xtrain[ele[0], ele[1]] = ele[2]
            data_train_index[ele[0], ele[1]] = 1

        # No test set, but still prepare the tensors
        Rtensor = torch.from_numpy(Xtrain.astype('float32')).to(args.device)
        data_train_index = torch.from_numpy(data_train_index.astype('float32')).to(args.device)

        # You can still use this combined input format if your model expects it
        Rtensor2 = torch.cat([Rtensor, data_train_index], axis=1)

        args.d = Rtensor.shape[1]
        test_loader = DataLoader(Rtensor2, 1, shuffle=False)
        
        model_name = "cvae"
        for l in args.layer:
            model_name += '_' + str(l)
        model_path = f"test_models/{model_name}.pth"
        model_eval = VAE(args).to(args.device)
        model_eval.load_state_dict(torch.load(model_path))

        preds = eval(test_loader, model_eval, loss=None)
        preds = preds.t()

        labeled_df = pd.DataFrame(preds.numpy(), 
                          index=df.index, 
                          columns=df.columns)
        output_path = os.path.join(directory, 'predictions.csv')
        labeled_df.to_csv(output_path)