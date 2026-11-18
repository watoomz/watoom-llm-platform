#include "WatooMPickup.h"
#include "WatooMCombatCharacter.h"
#include "WatooMCombatData.h"
#include "WatooMAttributeSet.h"
#include "AbilitySystemComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/RotatingMovementComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Net/UnrealNetwork.h"

AWatooMPickup::AWatooMPickup()
{
	bReplicates = true;
	SetReplicatingMovement(false);
	Trigger = CreateDefaultSubobject<USphereComponent>(TEXT("Trigger"));
	Trigger->InitSphereRadius(80.f);
	Trigger->SetCollisionProfileName(TEXT("OverlapAllDynamic"));
	Trigger->SetGenerateOverlapEvents(true);
	RootComponent = Trigger;
	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Trigger);
	Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Spin = CreateDefaultSubobject<URotatingMovementComponent>(TEXT("Spin"));
	Spin->RotationRate = FRotator(0.f, 90.f, 0.f);
}

void AWatooMPickup::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AWatooMPickup, Item);
	DOREPLIFETIME(AWatooMPickup, bAvailable);
}

void AWatooMPickup::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	ApplyLook();   // the mesh shows in the editor too, not only in play
}

void AWatooMPickup::BeginPlay()
{
	Super::BeginPlay();
	ApplyLook();
	if (HasAuthority()) { Trigger->OnComponentBeginOverlap.AddDynamic(this, &AWatooMPickup::OnOverlap); }
}

void AWatooMPickup::ApplyLook()
{
	UStaticMesh* M = Item ? Item->PickupMesh.Get() : nullptr;
	if (!M && Item && Item->Weapon) { M = Item->Weapon->StaticMesh.Get(); }
	Mesh->SetStaticMesh(M);
}

void AWatooMPickup::OnRep_Item() { ApplyLook(); }

void AWatooMPickup::OnRep_Available()
{
	SetActorHiddenInGame(!bAvailable);
}

void AWatooMPickup::SetAvailable(bool bNow)
{
	bAvailable = bNow;
	SetActorHiddenInGame(!bNow);
	Trigger->SetCollisionEnabled(bNow ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
	if (bNow)
	{
		// someone may be standing in it already
		TArray<AActor*> In;
		Trigger->GetOverlappingActors(In, AWatooMCombatCharacter::StaticClass());
		for (AActor* A : In) { if (GiveTo(Cast<AWatooMCombatCharacter>(A))) { break; } }
	}
}

void AWatooMPickup::OnOverlap(UPrimitiveComponent*, AActor* Other, UPrimitiveComponent*, int32, bool, const FHitResult&)
{
	GiveTo(Cast<AWatooMCombatCharacter>(Other));
}

static bool Restore(UAbilitySystemComponent* ASC, const FGameplayAttribute& Value, const FGameplayAttribute& Max, float Amount)
{
	if (Amount <= 0.f) { return false; }
	const float Now = ASC->GetNumericAttributeBase(Value);
	const float Cap = ASC->GetNumericAttribute(Max);
	if (Now >= Cap) { return false; }
	ASC->SetNumericAttributeBase(Value, FMath::Min(Now + Amount, Cap));
	return true;
}

bool AWatooMPickup::GiveTo(AWatooMCombatCharacter* C)
{
	if (!HasAuthority() || !bAvailable || !Item || !C || C->IsDead()) { return false; }
	UAbilitySystemComponent* ASC = C->GetAbilitySystemComponent();
	if (!ASC) { return false; }
	bool bUsed = false;
	switch (Item->Kind)
	{
	case EWatooMItemKind::Weapon:
		bUsed = Item->Weapon && C->AddWeapon(Item->Weapon) != INDEX_NONE;
		break;
	case EWatooMItemKind::Spell:
		if (Item->Spell) { C->AddSpell(Item->Spell); bUsed = true; }
		break;
	case EWatooMItemKind::Ammo:
		bUsed = C->AddReserveAmmoFor(Item->AmmoFor, Item->Ammo) > 0;
		break;
	case EWatooMItemKind::Consumable:
	{
		// each restore counts only if it changed something, so a full-health player walks over a medkit and leaves it
		const bool H = Restore(ASC, UWatooMAttributeSet::GetHealthAttribute(), UWatooMAttributeSet::GetMaxHealthAttribute(), Item->RestoreHealth);
		const bool S = Restore(ASC, UWatooMAttributeSet::GetShieldAttribute(), UWatooMAttributeSet::GetMaxShieldAttribute(), Item->RestoreShield);
		const bool M = Restore(ASC, UWatooMAttributeSet::GetManaAttribute(), UWatooMAttributeSet::GetMaxManaAttribute(), Item->RestoreMana);
		bUsed = H || S || M;
		break;
	}
	}
	if (!bUsed) { return false; }
	C->MulticastPlayFx(Item->PickupFx.Niagara, Item->PickupFx.Sound, GetActorLocation(), FRotator::ZeroRotator, Item->PickupFx.Scale);
	SetAvailable(false);
	if (RespawnSeconds > 0.f)
	{
		GetWorldTimerManager().SetTimer(RespawnTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { SetAvailable(true); }), RespawnSeconds, false);
	}
	return true;
}
