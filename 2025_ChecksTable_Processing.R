
##### Checks Table

setwd("C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/2025/2025_NUST_Processing/")

library(reshape2)

### Checks list obtained from 2025 list of entries checks list page

ChecksTable_2025_In0 <- read.csv("2025_List_of_Checks.csv")

ChecksTable_2025_In <- ChecksTable_2025_In0[-c(1:2),1:3]
colnames(ChecksTable_2025_In) <- ChecksTable_2025_In0[2,]

InTstLev <- levels(factor(ChecksTable_2025_In[,"Test"]))
TstLev <- unlist(lapply(InTstLev,function(x) unlist(strsplit(x,", "))))

colnames(ChecksTable_2025_In) <- gsub("Checks","Strain",colnames(ChecksTable_2025_In))

ChecksTable_2025_In$Strain <- gsub("\\(SCN\\)","",ChecksTable_2025_In$Strain) 
ChecksTable_2025_In$Strain <- gsub(" ","",ChecksTable_2025_In$Strain) 

ChecksTable_2025_In$Pheno1 <-  unlist(lapply(ChecksTable_2025_In$Strain,function(x) unlist(strsplit(x,"\\(|\\)")[[1]])[2]))
ChecksTable_2025_In$Pheno2 <-  unlist(lapply(ChecksTable_2025_In$Strain,function(x) unlist(strsplit(x,"\\(|\\)")[[1]])[4]))

Year <- "2025"
prTab_List <- list()
cnt <- 1

for(x in TstLev){
  
  pat<- paste("^\\b",x,"\\b$",sep="")
  lst <- strsplit(ChecksTable_2025_In[,"Test"],",")
  ind <- unlist(lapply(c(1:length(lst)),function(x) if(length(grep(pat,gsub(" ","",lst[[x]])))>=1){x}else{NULL}))
  Checks_Tst0 <- ChecksTable_2025_In[ind,] 
  StrRmInd <- which(Checks_Tst0[,"Strain"]=="" | is.na(Checks_Tst0[,"Strain"]))
  if(length(StrRmInd)>0){Checks_Tst <- Checks_Tst0[-StrRmInd,]}else{Checks_Tst <- Checks_Tst0}
  
  MGLevPat <- unlist(strsplit(x,"UT|PT"))
  MGLev <- paste("MG",MGLevPat[which(MGLevPat != "")],sep=" ")
  
  PhenotypeCol1 <-  paste(gsub(" ","",Checks_Tst[,"Pheno1"]),MGLev,sep="-")
  PhenotypeCol1Mod <-gsub("^[0-9]*-|^[I*V]*","",PhenotypeCol1) 
  
  #nonNull_Ind2 <- which(!(Checks_Tst[,"Pheno2"] %in% "") & Checks_Tst[,"Pheno2"] %in% " " & is.na(Checks_Tst[,"Pheno2"]))
  
  nonNull_Ind2 <-  grep("[A-Z]", Checks_Tst[,"Pheno2"])
  if(length(nonNull_Ind2) >0){PhenotypeCol2 <-  paste(gsub(" ","",Checks_Tst[nonNull_Ind2,"Pheno2"]),MGLev,sep="-")} else{PhenotypeCol2 <- ""}
  PhenotypeCol2Mod <-gsub("^[0-9]*-","",PhenotypeCol2) 
  
  PhenotypeColComb <- PhenotypeCol1Mod
  PhenotypeColComb[nonNull_Ind2] <- PhenotypeCol2Mod  #paste(PhenotypeCol1Mod[nonNull_Ind2],PhenotypeCol2Mod,sep="/")
  
  PhenotypeColComb <- gsub(paste("SCN-",MGLev,"|[/]|-TM|^-",sep=""),"",PhenotypeColComb)
  
  y <- cbind.data.frame(rep(Year,nrow(Checks_Tst)),rep(x,nrow(Checks_Tst)),Checks_Tst[,"Strain"],PhenotypeColComb,Checks_Tst[,"RM"])
  colnames(y) <- c("Year","Test","Strain","Phenotype","RM")
  rmInd.y <- unlist(apply(y,2,function(x) which(is.na(x) | x=="")))
  if(length(rmInd.y)>0){prTab_List[[cnt]]<- y[-rmInd.y,]}else{prTab_List[[cnt]]<- y}
  cnt <- cnt+1
}


TestsAllCombn <- unlist(lapply(c("UT","PT"),function(x) paste(x,c("00","00-TM","0","0-TM","I","I-TM","II","II-TM","III","III-TM","IV","IV-TM"),sep="")))
ChecksTable <- do.call(rbind,lapply(prTab_List,function(x) x))
ChecksTable$Phenotype <- gsub("NA-","",ChecksTable$Phenotype)

missingTests <- setdiff(TestsAllCombn,unique(ChecksTable[,"Test"]))

# write.csv(ChecksTable,"checksTable1.csv",row.names = FALSE)

### Fill in missing tests with equivalent tests 
ChecksTable1 <- ChecksTable
for(nMT in 1:length(missingTests)){ 
  if(length(grep("PT",missingTests[nMT]))>0){
    EqlntTest <- gsub("PT","UT",missingTests[nMT])
  }else if(length(grep("UT",missingTests[nMT]))>0){
    EqlntTest <- gsub("UT","PT",missingTests[nMT])
  }
  EqlntTestInd <- which(ChecksTable$Test %in% EqlntTest)
  missingTestData <- ChecksTable[EqlntTestInd,]
  missingTestData$Test <- missingTests[nMT]
  ChecksTable1 <- rbind.data.frame(ChecksTable1,missingTestData)
}

### Format Strain Names in Checks Table
ChecksTable1$OriginalStrain <- gsub("[- ]","",ChecksTable1$Strain)
ChecksTable1$Test <- gsub("-","",ChecksTable1$Test)

ChecksTable1$Strain <- gsub("[- ]","",ChecksTable1$Strain)
ChecksTable1 <- ChecksTable1[,c("Year","Test","Strain","OriginalStrain","Phenotype","RM")]


# Read the strains data
strainsTable1 <- read.csv("strainsTable1.csv", header = TRUE)

# Iterate over each check strain
for (nChks in seq_len(nrow(ChecksTable1))) {  
  chkStrn <- ChecksTable1$OriginalStrain[nChks]
  chkTst <- ChecksTable1$Test[nChks]
  
  # Construct the test pattern
  tstPatn <- paste0("^", chkTst, "$")
  
  # Find matches for strain and test in the strains table
  chkStrnInd <- grep(chkStrn, gsub("[- ]", "", strainsTable1$Strain))
  chkTstInd <- grep(tstPatn, strainsTable1$Test)
  
  # Handle potential mismatches by substituting "P" ↔ "U" if no test match is found
  if (length(chkTstInd) == 0) {
    if (grepl("P", tstPatn)) {
      tstPatn <- gsub("P", "U", tstPatn)
    } else if (grepl("U", tstPatn)) {
      tstPatn <- gsub("U", "P", tstPatn)
    }
    chkTstInd <- grep(tstPatn, strainsTable1$Test)
  }
  
  # Get intersection of matched strain and test indices
  ind <- intersect(chkStrnInd, chkTstInd)
  
  # Update the OriginalStrain value in ChecksTable1 if a match is found
  if (length(ind) > 0) {
    ChecksTable1$OriginalStrain[nChks] <- strainsTable1$OriginalStrain[ind[1]]
  }
}

# Clean and format the Strain column
ChecksTable1$Strain <- gsub("[- ]", "", ChecksTable1$Strain)

# Clean and format the Strain column
ChecksTable1$Strain <- gsub("\\([A-Z0-9]*\\)","", ChecksTable1$Strain)

# Select relevant columns
ChecksTable1 <- ChecksTable1[, c("Year", "Test", "Strain", "OriginalStrain", "Phenotype", "RM")]

####
write.csv(ChecksTable1,"checksTable1.csv",row.names = FALSE,quote=FALSE)
####  
