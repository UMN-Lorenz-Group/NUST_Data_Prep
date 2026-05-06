
### Check if all strains and locations are there in the final version of the data files
# i)

source("C:/Users/ivanv/Desktop/UMN_GIT/NUST_Data_Prep/nust_utils.R")

#### Strain List for 2022 NUST from Entry list files
setwd("C:/Users/ivanv/Desktop/UMN_Projects/NUST_GEI_Panel/2022/2022_NUST_Processing/2022_Strains_List/Strains_From_Ent_List/")

strainsEnt <- read.csv("strainsTableFromEntLists.csv",header=F)
colnames(strainsEnt) <- strainsEnt[1,]
strainsEnt <- strainsEnt[-1,]
strainsEntFilt <- strainsEnt[which(strainsEnt[,"Strain"] != ""),]
)

#### Strain List for 2022 NUST from Data list files 

setwd("C:/Users/ivanv/Desktop/UMN_Projects/NUST_GEI_Panel/2022/2022_NUST_Processing/2022_Strains_List/")
strainsDat <- read.csv("strainsTableFromDataFiles.csv",header=T)


#### Read in Data Tables 
setwd("C:/Users/ivanv/Desktop/UMN_Projects/NUST_GEI_Panel/2022/")

checksTable <- read.csv("checksTable1.csv",header=T)
strainsTable <- read.csv("strainsTable1.csv",header=T)
locationsTable <- read.csv("locationsTable1.csv",header=T)
phenotypesTable <- read.csv("phenotypesTable1.csv",header=T)

###
length(unique(phenotypesTable[,"Strain"]))
datStrains <- unique(phenotypesTable[,"Strain"])

#### 

#### Format strains from data table 

datStrains <- clean_strain_annotations(datStrains)
datStrains <- datStrains[which(!duplicated(datStrains))]

ChecksTable <- checksTable[which(!duplicated(checksTable$Strain)),]
checksTable$Strain <- gsub(" ","",checksTable$Strain)

#### Format strains from entry list table 

length(strainsEntFilt[,"Strain"])
length(unique(strainsEntFilt[,"Strain"]))
entListStrains <- unique(strainsEntFilt[,"Strain"])

entListStrains <- clean_strain_annotations(entListStrains)
entListStrains <- entListStrains[which(!duplicated(entListStrains))]

###

DiffStrn1 <- setdiff(entListStrains,unique(datStrains))
length(DiffStrn1)

#### Format DiffStrain
DiffStrn1 <- clean_strain_annotations(DiffStrn1)
DiffStrn1 <- DiffStrn1[which(!duplicated(DiffStrn1))]

length(DiffStrn1)
# [1] 20

diffStrnDatInd <- unlist(lapply(unique(DiffStrn1),function(x) grep(x,datStrains)))

####
diffStrnChkInd <- lapply(unique(ChecksTable$Strain),function(x) grep(x,DiffStrn1))
length(unique(unlist(diffStrnChkInd)))

diffStrnChkNames <- unlist(lapply(unique(ChecksTable$Strain),function(x) grep(x,DiffStrn1,value=T)))
setdiff(DiffStrn1,diffStrnChkNames)

####
strainsEntFilt[,"Strain"] <- gsub("\\(.*\\)","",strainsEntFilt[,"Strain"])
grep("\\(",strainsEntFilt$Strain)

strainsEntFilt$Strain <- gsub(" ","",strainsEntFilt$Strain) 

strainsEntFilt$Test[which(strainsEntFilt$Strain %in% DiffStrn1)]

##### 


strainsTable1 <- read.csv("strainsTable1.csv",header=T) 
length(unique(strainsTable1[,"Strain"]))

strainsTableStrn1 <- unique(strainsTable1[,"Strain"]) 
strainsTable1$Strain[which(strainsTable1[,"Strain"] %in% "F5" | strainsTable1[,"Strain"] %in% "F6" |strainsTable1[,"Strain"] %in% ""|strainsTable1[,"Strain"] %in% " Rps")]
strFiltInd <- which(strainsTable1[,"Strain"] %in% "F5" | strainsTable1[,"Strain"] %in% "F6" |strainsTable1[,"Strain"] %in% ""|strainsTable1[,"Strain"] %in% " Rps")
if(length(strFiltInd) >0){strainsTable1Filt <- strainsTable1[-strFiltInd,]}else{strainsTable1Filt <- strainsTable1} 

###

strainsTableStrn1 <- clean_strain_annotations(unique(strainsTable1Filt[,"Strain"]))

strainsTableStrn1 <- strainsTableStrn1[which(!duplicated(strainsTableStrn1))]

### The below three checks should result in empty values 
setdiff(unique(entListStrains),unique(strainsTableStrn1))
setdiff(unique(strainsTableStrn1),entListStrains)
grep("Rps",strainsTable1Filt[,"Strain"])

###
write.csv(strainsTable1Filt,"strainsTable1.csv",row.names=F,quote=F)

###
### Locations Table  
setdiff(unique(strainsTable1Filt[,"Strain"]),entListStrains)