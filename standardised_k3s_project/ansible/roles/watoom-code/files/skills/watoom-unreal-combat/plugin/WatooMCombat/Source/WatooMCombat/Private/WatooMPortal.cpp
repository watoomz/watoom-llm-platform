#include "WatooMPortal.h"
#include "Components/BoxComponent.h"
#include "NiagaraComponent.h"
#include "NiagaraSystem.h"
#include "GameFramework/Pawn.h"
#include "Engine/World.h"

namespace
{
	// last teleport time per pawn, shared by every portal (a destination on another portal must not bounce the pawn back)
	TMap<TWeakObjectPtr<APawn>, double> GLastSent;
}

AWatooMPortal::AWatooMPortal()
{
	bReplicates = true;
	Box = CreateDefaultSubobject<UBoxComponent>(TEXT("Box"));
	Box->SetBoxExtent(BoxExtent);
	Box->SetCollisionProfileName(TEXT("Trigger"));
	Box->SetGenerateOverlapEvents(true);
	RootComponent = Box;
	FxComponent = CreateDefaultSubobject<UNiagaraComponent>(TEXT("Fx"));
	FxComponent->SetupAttachment(Box);
	FxComponent->bAutoActivate = false;
}

void AWatooMPortal::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	Box->SetBoxExtent(BoxExtent);
	FxComponent->SetAsset(Fx);
}

void AWatooMPortal::BeginPlay()
{
	Super::BeginPlay();
	Box->SetBoxExtent(BoxExtent);
	if (Fx) { FxComponent->SetAsset(Fx); FxComponent->Activate(true); }
	if (HasAuthority()) { Box->OnComponentBeginOverlap.AddDynamic(this, &AWatooMPortal::OnOverlap); }
}

void AWatooMPortal::OnOverlap(UPrimitiveComponent*, AActor* Other, UPrimitiveComponent*, int32, bool, const FHitResult&)
{
	if (APawn* Pawn = Cast<APawn>(Other)) { Send(Pawn); }
}

bool AWatooMPortal::Send(APawn* Pawn)
{
	if (!Pawn || !HasAuthority()) { return false; }
	const double Now = GetWorld()->GetTimeSeconds();
	if (const double* Last = GLastSent.Find(Pawn); Last && Now - *Last < CooldownSeconds && Now >= *Last) { return false; }
	GLastSent.Add(Pawn, Now);
	const FRotator Facing(0.f, DestinationYaw, 0.f);
	const bool bMoved = Pawn->TeleportTo(Destination, Facing);
	if (bMoved && Pawn->GetController()) { Pawn->GetController()->SetControlRotation(Facing); }
	return bMoved;
}
