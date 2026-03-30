### Checks
## Check if the files contain complete data available
## All strains present in phenotable and strainstable
## all phenotypes in correct format
## all locations present with complete information
## all checks present with complete information

source("C:/Users/ivanv/Desktop/UMN_GIT/NUST_Data_Prep/nust_utils.R")
phenoTab1 <- read.csv("phenotypesTable0.csv")
length(unique(phenoTab1$Strain))
#[1] 414

length(unique(phenoTab1$OriginalStrain))
# [1] 426
 
###
 strainsTab1 <- read.csv("strainsTable1.csv")
 length(unique(strainsTab1$Strain))
 #[1] 412

 length(unique(strainsTab1$OriginalStrain))
 #[1] 421

###  
strainsTabFile <- read.csv("strainsTable_From_DataFiles.csv")
length(unique(strainsTabFile$Strain))
#[1] 412

length(unique(strainsTabFile$OriginalStrain))
#[1] 421


### Remove non-strain IDs in table from phenotypesTable1.csv

phenoTab1$Strain <- gsub("\\(GTSCN\\)","",phenoTab1$Strain)
#dPh1
#[1] NA          "Reps"      "Rows/Plot"

phenoTab1$Strain <- gsub("[\\*]*\\*$","",(phenoTab1$Strain))


phenoTab1$Strain <- gsub("--$","",phenoTab1$Strain)
phenoTab1$Strain <- gsub("-$","",phenoTab1$Strain)


dPh1 <- setdiff(unique(phenoTab1$Strain),unique(strainsTab1$Strain))

phenoTab1$Strain <- gsub("NDDickey","ND-Dickey",phenoTab1$Strain)
# strainsTab1$Strain <- gsub("OAC","OAC-",strainsTab1$Strain)
# strainsTab1$Strain <- gsub("ORC","ORC-",strainsTab1$Strain)
# strainsTab1$Strain <- gsub("NDRolette","ND-Rolette",strainsTab1$Strain)
# strainsTab1$Strain <- gsub("NDDickey","ND-Dickey",strainsTab1$Strain)

##
dS1 <- setdiff(unique(strainsTab1$Strain),unique(phenoTab1$Strain))


naInd1 <- which(is.na(phenoTab1$Strain))
patToRm <- c("Reps","Rows/Plot")
patToRmInd <- unlist(lapply(patToRm,function(x) grep(x,phenoTab1$Strain)))

rmPhInd <- patToRmInd
if(length(rmPhInd) >0){ phenoTab1_Filt <- phenoTab1[-rmPhInd,]}else{phenoTab1_Filt <- phenoTab1}

dim(phenoTab1_Filt)
#[1] 4854   25


####Match # strains in strains table and phenotypes table 
unqStrn_StrnTab <- unique(strainsTabFile$Strain)
phenoTab1_Filt$Strain <- gsub("[\\*]*$","",phenoTab1_Filt$Strain)
 
unqStrn_PhTab <- unique(phenoTab1_Filt$Strain)
length(unqStrn_PhTab)
#[1] 412
length(unqStrn_StrnTab)
#[1] 412
 
### 412 unique strains in the phenotypes and strain tables
 length(unique(phenoTab1_Filt$OriginalStrain))
 #426

 unqOriStrn_PhTab <- unique(phenoTab1_Filt$OriginalStrain)
 length(unique(strainsTab1$OriginalStrain))
 #[1] 421
 
###  unique original strain IDs in the phenotypes and strains table 
 
 length(unqOriStrn_PhTab)
 #[1] 426
 length(unique(strainsTab1$OriginalStrain))
 #[1] 421
 
##
 setdiff(unique(strainsTab1$OriginalStrain),unique(phenoTab1_Filt$OriginalStrain))
 #character(0)
 setdiff(unique(phenoTab1_Filt$OriginalStrain),unique(strainsTab1$OriginalStrain))
 #character(0)
 
 
strnsTabOri <-  unique(strainsTab1$OriginalStrain)
StrnsTabOri <- gsub(" ","",strnsTabOri)
setdiff(unique(StrnsTabOri),unique(phenoTab1_Filt$OriginalStrain))
setdiff(unique(phenoTab1_Filt$OriginalStrain),unique(StrnsTabOri))

### Final format for phenotypesTable1.csv
 
### Rm original strain column 

phenoTab2_Filt<- phenoTab1_Filt[,-which(colnames(phenoTab1_Filt) %in% "OriginalStrain")]
 
## PhenoTable long format 
 
phenoTab1_Filt_Long <- melt(phenoTab2_Filt,id.vars=c("Strain","Year","Test","Location","City","State"))
colnames(phenoTab1_Filt_Long) <- c("Strain","Year","Test","Location","City","State","Phenotype","Value")

####

##

### Get Phenotype-Units from 2023
pheno23 <- read.csv("phenotypesTable1_2023.csv")
pheno23$PhenoUnits <- paste(pheno23$Phenotype,pheno23$Units,sep="-")
PhUnits <- levels(factor(pheno23$PhenoUnits)) 

PhUnitsTab <- do.call(rbind.data.frame,lapply(PhUnits,function(x) unlist(strsplit(x,"-"))))
colnames(PhUnitsTab)<- c("Pheno","Units")
PhUnitsTab[1:5,]

phenoTab1_Filt_Long$Units <- NA

for(nR in 1:nrow(PhUnitsTab)){
  
  phInd <- which(phenoTab1_Filt_Long$Phenotype == PhUnitsTab$Pheno[nR])
  if(length(phInd) >=1){
    phenoTab1_Filt_Long$Units[phInd] <-   PhUnitsTab$Units[nR]
  }
}


#### 

df <- phenoTab1_Filt_Long
# Unify location names
df$City <- standardize_location_names(df$City)

# Standardize state names
phenoTab1_Long0 <- df

rmIndFin <- which(phenoTab1_Long0$City %in% "")
 if(length(rmIndFin) >1){phenoTable1_Long <- phenoTab1_Long0[-rmIndFin,-which(colnames(phenoTab1_Long0) %in% "Location")]}else{phenoTable1_Long <- phenoTab1_Long0}

###
length(unique(phenoTable1_Long$Strain))
#[1] 412
length(unique(phenoTable1_Long$Location))
#[1]  46

phenoTable1_Long$City <- gsub("Steven's","Stevens",phenoTable1_Long$City)
length(unique(phenoTable1_Long$City))
#[1] 43

#write.csv(phenoTable1_Long,"phenotypesTable1.csv",row.names=FALSE,quote=FALSE)

####

phenoTable1_Long$Strain <- gsub("OAC-","OAC ",phenoTable1_Long$Strain)
phenoTable1_Long$Strain <- gsub("ORC-","ORC ",phenoTable1_Long$Strain)
phenoTable1_Long$Strain <- gsub("ND-Dickey","ND Dickey",phenoTable1_Long$Strain)
phenoTable1_Long$Strain <- gsub("NDRolette","ND Rolette",phenoTable1_Long$Strain)



# phenoTable1_Long$OriginalStrain <- gsub("OAC-","OAC ",phenoTable1_Long$OriginalStrain)
# phenoTable1_Long$OriginalStrain <- gsub("ORC-","ORC ",phenoTable1_Long$OriginalStrain)
# phenoTable1_Long$OriginalStrain <- gsub("ND-Dickey","ND Dickey",phenoTable1_Long$OriginalStrain)
# phenoTable1_Long$OriginalStrain <- gsub("NDRolette","ND Rolette",phenoTable1_Long$OriginalStrain)

setwd("C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/2025/2025_NUST_Processing/Files4Upload/")


write.csv(phenoTable1_Long,"phenotypesTable1.csv",row.names=FALSE,quote=FALSE)

###
strainsTab1$Strain <- gsub("OAC","OAC ",strainsTab1$Strain)
strainsTab1$Strain <- gsub("ORC","ORC ",strainsTab1$Strain)
strainsTab1$Strain <- gsub("NDDickey","ND Dickey",strainsTab1$Strain)
strainsTab1$Strain <- gsub("NDRolette","ND Rolette",strainsTab1$Strain)
##
strainsTab1$OriginalStrain <- gsub("OAC","OAC ",strainsTab1$OriginalStrain)
strainsTab1$OriginalStrain <- gsub("ORC","ORC ",strainsTab1$OriginalStrain)
strainsTab1$OriginalStrain <- gsub("NDDickey","ND Dickey",strainsTab1$OriginalStrain)
strainsTab1$OriginalStrain <- gsub("NDRolette","ND Rolette",strainsTab1$OriginalStrain)

length(unique(strainsTab1$Strain))
#[1] 412
write.csv(strainsTab1,"strainsTable1.csv",quote=FALSE,row.names=FALSE)
 

parTab1 <- read.csv("parentageTable1.csv")

parTab1$Strain 
###
parTab1$Strain  <- gsub("OAC","OAC ",parTab1$Strain)
parTab1$Strain <- gsub("ORC","ORC ",parTab1$Strain)
parTab1$Strain <- gsub("NDDickey","ND Dickey",parTab1$Strain)
parTab1$Strain <- gsub("NDRolette","ND Rolette",parTab1$Strain)

write.csv(parTab1,"parentageTable1.csv",quote=FALSE,row.names=FALSE)

###

#Checks Table

chksTable <- read.csv("checksTable1.csv")

chksTable$OriginalStrain<- gsub("NDDickey","ND Dickey",chksTable$OriginalStrain)
chksTable$Strain<- gsub("NDDickey","ND Dickey",chksTable$Strain)
chksTable$Strain<- gsub("NDRolette","ND Rolette",chksTable$Strain)

write.csv(chksTable,"checksTable1.csv",quote=FALSE,row.names=FALSE)




table(phenoTable1_Long$Year)
# 2025 
# 87372
 
anyNA(phenoTable1_Long$Year)
#[1] FALSE
